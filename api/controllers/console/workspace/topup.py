"""Workspace wallet and top-up endpoints.

Surfaces the workspace-level ``TenantBalance`` (balance / locked /
total_topup) together with the caller's own ``UserBalance`` so the
frontend wallet widget can render both in a single request.

Any member of the workspace may read their wallet; topup endpoints
(creation, listing, detail, close) are gated on the OWNER role via
``@tenant_owner_required`` — only the workspace owner can move funds
into or out of the workspace wallet.

Amount contract: API accepts and returns ``amount_fen`` as ``int``.
This avoids float rounding on the wire and matches Alipay's internal
(yuan / 100) representation. Decimal yuan strings are exposed
alongside for display only.
"""

from __future__ import annotations

from flask import request
from flask_restx import Resource
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
    tenant_owner_required,
)
from libs.exception import BaseHTTPException
from libs.login import current_account_with_tenant, login_required
from services.payment.exceptions import (
    AmountTooLarge,
    AmountTooSmall,
    OrderAlreadyClosed,
    OrderNotFound,
    PaymentDisabled,
    ProviderBusinessError,
)
from services.payment.payment_service import PaymentService
from services.user_billing_service import UserBillingService
from services.wallet.tenant_balance_service import TenantBalanceService

# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class PaymentDisabledHTTPError(BaseHTTPException):
    error_code = "payment_disabled"
    description = "Top-up is currently disabled. Please contact the administrator."
    code = 503


class TopupAmountInvalidError(BaseHTTPException):
    error_code = "topup_amount_invalid"
    description = "Top-up amount is invalid for the configured bounds."
    code = 400


class TopupOrderNotFoundError(BaseHTTPException):
    error_code = "topup_order_not_found"
    description = "Top-up order not found."
    code = 404


class TopupOrderAlreadyClosedError(BaseHTTPException):
    error_code = "topup_order_already_closed"
    description = "Top-up order is not in a closable state."
    code = 409


class TopupProviderError(BaseHTTPException):
    error_code = "topup_provider_error"
    description = "The payment provider rejected the request."
    code = 502


# ---------------------------------------------------------------------------
# Request payloads
# ---------------------------------------------------------------------------


class CreateTopupOrderPayload(BaseModel):
    """Topup request body.

    ``amount_fen`` is the raw integer amount in cents so callers can't send
    floats (which would be rounded on the wire). ``subject`` is user-visible
    in the Alipay cashier page; keep it short and neutral.

    ``strict=True`` prevents Pydantic v2's default lax coercion from turning
    ``"100"`` into ``100`` — we want integer-only on the wire so the schema
    is unambiguous and a single source of truth for the frontend.
    """

    model_config = ConfigDict(strict=True)

    amount_fen: int = Field(..., gt=0, le=10_000_000)
    subject: str = Field(default="钱包充值", min_length=1, max_length=256)


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------


def _tenant_balance_payload(tenant_id: str) -> dict:
    balance = TenantBalanceService.get_or_create(tenant_id)
    return {
        "tenant_id": balance.tenant_id,
        "balance": str(balance.balance),
        "locked": str(balance.locked),
        "total_topup": str(balance.total_topup),
        "total": str(balance.total),
        "currency": balance.currency,
        "updated_at": balance.updated_at.isoformat(),
    }


def _user_balance_payload(account_id: str) -> dict:
    balance = UserBillingService.get_or_create_balance(account_id)
    return {
        "account_id": balance.account_id,
        "balance": str(balance.balance),
        "currency": balance.currency,
        "is_sufficient": balance.is_sufficient(),
        "updated_at": balance.updated_at.isoformat(),
    }


def _order_payload(order) -> dict:
    """Serialise a PaymentOrder row for the console API.

    We only expose the QR / pay_url returned at creation time. The raw
    Alipay payloads (``prepay_raw``, ``notify_raw``) are intentionally
    omitted — they contain signatures and are for backend audit only.
    """
    return {
        "order_id": order.id,
        "out_trade_no": order.out_trade_no,
        "provider": order.provider,
        "provider_trade_no": order.provider_trade_no,
        "tenant_id": order.tenant_id,
        "account_id": order.account_id,
        "amount": str(order.amount),
        "amount_fen": order.amount_fen,
        "subject": order.subject,
        "status": order.status,
        "qr_code": order.qr_code,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "expires_at": order.expires_at.isoformat() if order.expires_at else None,
        "created_at": order.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@console_ns.route("/workspaces/current/wallet")
class WorkspaceWalletApi(Resource):
    """Return the current workspace wallet plus the caller's member balance."""

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        current_user, current_tenant_id = current_account_with_tenant()
        return {
            "tenant": _tenant_balance_payload(current_tenant_id),
            "user": _user_balance_payload(current_user.id),
        }, 200


@console_ns.route("/workspaces/current/topup/orders")
class TopupOrderListApi(Resource):
    """Create and list top-up orders for the current workspace."""

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    def post(self):
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            payload = CreateTopupOrderPayload.model_validate(request.get_json() or {})
        except ValidationError as e:
            raise TopupAmountInvalidError(str(e))

        service = PaymentService.from_config()
        try:
            result = service.create_order(
                tenant_id=current_tenant_id,
                account_id=current_user.id,
                amount_fen=payload.amount_fen,
                subject=payload.subject,
                client_ip=request.remote_addr,
            )
        except PaymentDisabled as e:
            raise PaymentDisabledHTTPError(str(e))
        except (AmountTooSmall, AmountTooLarge) as e:
            raise TopupAmountInvalidError(str(e))
        except ProviderBusinessError as e:
            raise TopupProviderError(str(e))
        return result, 201

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """Any workspace member can view the top-up history for audit."""
        _, current_tenant_id = current_account_with_tenant()
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
        orders, total = PaymentService.from_config().list_tenant_orders(
            tenant_id=current_tenant_id,
            limit=limit,
            offset=offset,
        )
        return {
            "data": [_order_payload(o) for o in orders],
            "total": total,
            "limit": limit,
            "offset": offset,
        }, 200


@console_ns.route("/workspaces/current/topup/orders/<string:out_trade_no>")
class TopupOrderDetailApi(Resource):
    """Fetch a single top-up order scoped to the current workspace."""

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, out_trade_no: str):
        _, current_tenant_id = current_account_with_tenant()
        try:
            order = PaymentService.from_config().get_order(
                tenant_id=current_tenant_id, out_trade_no=out_trade_no
            )
        except OrderNotFound:
            raise TopupOrderNotFoundError()
        return _order_payload(order), 200


@console_ns.route("/workspaces/current/topup/orders/<string:out_trade_no>/close")
class TopupOrderCloseApi(Resource):
    """Close a pending top-up order (owner only)."""

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    def post(self, out_trade_no: str):
        _, current_tenant_id = current_account_with_tenant()
        try:
            order = PaymentService.from_config().close_order(
                tenant_id=current_tenant_id, out_trade_no=out_trade_no
            )
        except OrderNotFound:
            raise TopupOrderNotFoundError()
        except OrderAlreadyClosed:
            raise TopupOrderAlreadyClosedError()
        return _order_payload(order), 200
