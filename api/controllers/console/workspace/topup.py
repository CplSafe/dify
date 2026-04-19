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

import json

from flask import request
from flask_restx import Resource, fields
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
# Swagger 模型定义（模块级）
# ---------------------------------------------------------------------------

tenant_balance_model = console_ns.model(
    "TenantBalance",
    {
        "tenant_id": fields.String(description="工作空间 ID"),
        "balance": fields.String(description="可用余额（元）"),
        "locked": fields.String(description="锁定中的金额（元）"),
        "total_topup": fields.String(description="累计充值总额（元）"),
        "total": fields.String(description="总余额（可用 + 锁定，元）"),
        "currency": fields.String(description="货币单位，默认 CNY"),
        "updated_at": fields.String(description="最后更新时间 ISO8601"),
    },
)

user_balance_model = console_ns.model(
    "UserBalance",
    {
        "account_id": fields.String(description="成员账号 ID"),
        "balance": fields.String(description="当前余额（元）"),
        "currency": fields.String(description="货币单位，默认 CNY"),
        "is_sufficient": fields.Boolean(description="余额是否足够（用于前端提示）"),
        "updated_at": fields.String(description="最后更新时间 ISO8601"),
    },
)

wallet_resp = console_ns.model(
    "WalletResp",
    {
        "tenant": fields.Nested(tenant_balance_model, description="工作空间钱包信息"),
        "user": fields.Nested(user_balance_model, description="当前成员钱包信息"),
    },
)

topup_order_create_req = console_ns.model(
    "TopupOrderCreateReq",
    {
        "amount_fen": fields.Integer(
            required=True,
            description="充值金额（分，整数），最小 1，最大 10,000,000",
            example=10000,
        ),
        "subject": fields.String(
            required=False,
            description="支付宝收银台显示的商品名称，默认「钱包充值」，最多 256 字符",
            example="钱包充值",
        ),
    },
)

order_item = console_ns.model(
    "TopupOrderItem",
    {
        "order_id": fields.String(description="系统订单 ID"),
        "out_trade_no": fields.String(description="商户唯一交易流水号"),
        "provider": fields.String(description="支付渠道，如 alipay"),
        "provider_trade_no": fields.String(description="支付宝/支付渠道侧交易号，支付前为 null"),
        "tenant_id": fields.String(description="工作空间 ID"),
        "account_id": fields.String(description="发起充值的成员账号 ID"),
        "amount": fields.String(description="充值金额（元）"),
        "amount_fen": fields.Integer(description="充值金额（分）"),
        "subject": fields.String(description="订单标题"),
        "status": fields.String(
            description="订单状态：pending / paid / closed / expired"
        ),
        "qr_code": fields.String(description="二维码渠道的支付二维码内容（base64 或 URL）"),
        "pay_url": fields.String(description="页面跳转渠道的支付链接"),
        "paid_at": fields.String(description="支付完成时间 ISO8601，未支付为 null"),
        "expires_at": fields.String(description="订单过期时间 ISO8601"),
        "created_at": fields.String(description="订单创建时间 ISO8601"),
    },
)

order_list_resp = console_ns.model(
    "TopupOrderListResp",
    {
        "data": fields.List(fields.Nested(order_item), description="订单列表"),
        "total": fields.Integer(description="总订单数"),
        "limit": fields.Integer(description="每页条数"),
        "offset": fields.Integer(description="偏移量"),
    },
)

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


def _extract_pay_url(order) -> str | None:
    """Pull ``pay_url`` out of a page-channel order's prepay_raw envelope.

    Page-channel orders store ``{"pay_url": "..."}`` JSON on ``prepay_raw``
    (see :class:`AlipayPageProvider`). QR-channel orders use ``qr_code``
    instead and have no ``pay_url``. Returning ``None`` for QR / malformed
    envelopes is deliberate — the frontend checks ``qr_code`` first.
    """
    raw = order.prepay_raw
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    url = data.get("pay_url") if isinstance(data, dict) else None
    return url if isinstance(url, str) else None


def serialize_order(order) -> dict:
    """Serialise a PaymentOrder row for the console API.

    Exposes ``qr_code`` (QR channel) and ``pay_url`` (page channel) so the
    frontend can resume a pending order without re-creating it. The raw
    Alipay payloads (``prepay_raw``, ``notify_raw``) stay server-side —
    they carry signatures and are for backend audit only.

    Exported (not underscore-prefixed) so the super-admin order-list endpoint
    in ``creator/balance.py`` can share the exact same shape — if one caller
    ever needs a different subset, split into two serialisers rather than
    letting the shapes silently diverge.
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
        "pay_url": _extract_pay_url(order),
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
    @console_ns.doc(
        description="获取当前工作空间钱包余额及当前登录成员的个人余额（所有成员均可访问）",
        responses={
            200: ("成功", wallet_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(wallet_resp)
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
    @console_ns.doc(
        description="发起充值订单，返回支付宝收银台二维码或跳转链接（仅工作空间所有者可操作）",
        responses={
            201: ("创建成功，返回订单信息", order_item),
            400: "金额参数无效（低于最小限额或超过最大限额）",
            401: "未登录",
            403: "仅工作空间所有者可操作",
            502: "支付渠道业务异常",
            503: "充值功能未启用",
        },
    )
    @console_ns.expect(topup_order_create_req, validate=False)
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
    @tenant_owner_required
    @console_ns.doc(
        description="获取当前工作空间的充值订单列表，按创建时间倒序（仅工作空间所有者可操作）",
        params={
            "limit": "每页条数，最大 100，默认 20",
            "offset": "分页偏移量，默认 0",
            "status": "可选，按状态过滤：pending / paid / closed / expired",
        },
        responses={
            200: ("成功", order_list_resp),
            401: "未登录",
            403: "仅工作空间所有者可操作",
        },
    )
    @console_ns.marshal_with(order_list_resp)
    def get(self):
        """Owner-only: list top-up orders for the workspace.

        Restricted to owner because the order stream exposes per-topup
        amounts and timestamps — financial info members don't need.
        Aggregate balance is still visible via ``/workspaces/current/wallet``.
        """
        _, current_tenant_id = current_account_with_tenant()
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
        status = request.args.get("status") or None
        orders, total = PaymentService.from_config().list_tenant_orders(
            tenant_id=current_tenant_id,
            limit=limit,
            offset=offset,
            status=status,
        )
        return {
            "data": [serialize_order(o) for o in orders],
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
    @tenant_owner_required
    @console_ns.doc(
        description="按商户交易流水号查询单条充值订单详情（仅工作空间所有者可操作）",
        responses={
            200: ("成功", order_item),
            401: "未登录",
            403: "仅工作空间所有者可操作",
            404: "订单不存在",
        },
    )
    @console_ns.marshal_with(order_item)
    def get(self, out_trade_no: str):
        """Owner-only: fetch a single top-up order. Same rationale as the
        list endpoint — the QR code / amount / status are owner-scoped."""
        _, current_tenant_id = current_account_with_tenant()
        try:
            order = PaymentService.from_config().get_order(
                tenant_id=current_tenant_id, out_trade_no=out_trade_no
            )
        except OrderNotFound:
            raise TopupOrderNotFoundError()
        return serialize_order(order), 200


@console_ns.route("/workspaces/current/topup/orders/<string:out_trade_no>/close")
class TopupOrderCloseApi(Resource):
    """Close a pending top-up order (owner only)."""

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    @console_ns.doc(
        description="主动关闭待支付的充值订单（无请求体）。已关闭/已支付/已过期订单不可重复关闭（仅工作空间所有者可操作）",
        responses={
            200: ("关闭成功，返回订单最新状态", order_item),
            401: "未登录",
            403: "仅工作空间所有者可操作",
            404: "订单不存在",
            409: "订单状态不允许关闭",
        },
    )
    @console_ns.marshal_with(order_item)
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
        return serialize_order(order), 200
