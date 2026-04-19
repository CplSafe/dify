"""User balance and billing record endpoints."""

from decimal import Decimal, InvalidOperation

from flask import request
from flask_restx import Resource

from controllers.console import console_ns
from controllers.console.creator.models import (
    admin_balance_list_resp,
    admin_topup_req,
    balance_resp,
    billing_record_list_resp,
    topup_order_list_resp,
)
from controllers.console.workspace.topup import serialize_order
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from services.payment.payment_service import PaymentService
from services.user_billing_service import UserBillingService
from services.wallet.tenant_balance_service import TenantBalanceService


def _require_system_admin(user):
    if not user.is_system_admin:
        from werkzeug.exceptions import Forbidden
        raise Forbidden("Only system administrators can access this endpoint")


@console_ns.route("/creator/balance")
class UserBalanceApi(Resource):
    """Get the caller's effective spendable balance.

    Two branches, same response shape:

    - **Owner** — returns ``TenantBalance.balance`` (workspace spendable
      pool). Owners draw workflow costs directly from this wallet; a
      per-user ``UserBalance`` would never be read and so is never
      created here.
    - **Member** — returns the caller's ``UserBalance`` (their personal
      allocation from the workspace pool).

    ``account_id`` is always the caller's id. ``is_sufficient`` is
    derived from whichever wallet is authoritative for that role.
    """

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="获取当前用户的可用余额。Owner 返回工作空间余额池，Member 返回个人分配余额。",
        responses={
            200: ("成功", balance_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(balance_resp)
    def get(self):
        """获取当前用户的余额"""
        current_user, current_tenant_id = current_account_with_tenant()

        if UserBillingService.is_tenant_owner(current_user.id, current_tenant_id):
            tenant_balance = TenantBalanceService.get_or_create(current_tenant_id)
            return {
                "account_id": current_user.id,
                "balance": str(tenant_balance.balance),
                "currency": tenant_balance.currency,
                "is_sufficient": tenant_balance.balance > Decimal(0),
            }

        balance = UserBillingService.get_or_create_balance(current_user.id)
        return {
            "account_id": balance.account_id,
            "balance": str(balance.balance),
            "currency": balance.currency,
            "is_sufficient": balance.is_sufficient(),
        }


@console_ns.route("/creator/admin/balances")
class AdminBalancesApi(Resource):
    """List every account's authoritative wallet balance (super admin only).

    Enumerates accounts (not wallet rows) so newly-registered owners — who
    don't yet have a ``UserBalance`` row because owners draw from
    ``TenantBalance`` instead — remain visible. Previously the admin view
    silently dropped these users until their first tenant-wallet write
    materialised the row.
    """

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="管理员查看所有用户余额列表（仅超级管理员可用）。",
        params={
            "limit": "每页条数，最大 100，默认 50",
            "offset": "偏移量，默认 0",
        },
        responses={
            200: ("成功", admin_balance_list_resp),
            403: "无权限（非超级管理员）",
        },
    )
    @console_ns.marshal_with(admin_balance_list_resp)
    def get(self):
        """管理员获取所有用户余额列表"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))

        rows, total = UserBillingService.list_admin_account_balances(
            limit=limit, offset=offset
        )
        return {
            "data": [
                {
                    "account_id": r.account_id,
                    "account_name": r.account_name,
                    "account_email": r.account_email,
                    "role": r.role,
                    "tenant_id": r.tenant_id,
                    "balance": str(r.balance),
                    "currency": r.currency,
                    "is_sufficient": r.is_sufficient,
                    # Null updated_at means the wallet row hasn't been created
                    # yet (fresh owner pre-first-top-up). Empty string rather
                    # than None keeps the response shape stable for the UI.
                    "updated_at": r.updated_at.isoformat() if r.updated_at else "",
                }
                for r in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@console_ns.route("/creator/admin/topup")
class AdminTopupApi(Resource):
    """Top up a user's balance (super admin only)."""

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="管理员为指定用户充值余额（仅超级管理员可用）。",
        responses={
            201: "充值成功，返回账单记录",
            400: "参数缺失或金额格式错误",
            403: "无权限",
        },
    )
    @console_ns.expect(admin_topup_req, validate=False)
    def post(self):
        """管理员为用户充值"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        payload = request.get_json() or {}
        account_id = payload.get("account_id")
        raw_amount = payload.get("amount")
        description = payload.get("description", "")

        if not account_id or raw_amount is None:
            from werkzeug.exceptions import BadRequest
            raise BadRequest("account_id and amount are required")

        try:
            amount = Decimal(str(raw_amount))
        except InvalidOperation:
            from werkzeug.exceptions import BadRequest
            raise BadRequest("Invalid amount")

        record = UserBillingService.topup(
            account_id=account_id,
            amount=amount,
            description=description,
        )
        return record.to_dict(), 201


@console_ns.route("/creator/billing/records")
class BillingRecordsApi(Resource):
    """List billing records for the current user."""

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="获取当前用户的账单记录（充值、消费、返佣等）。",
        params={
            "limit": "每页条数，最大 100，默认 50",
            "offset": "偏移量，默认 0",
        },
        responses={
            200: ("成功", billing_record_list_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(billing_record_list_resp)
    def get(self):
        """获取当前用户的账单记录"""
        current_user, _ = current_account_with_tenant()
        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))

        records, total = UserBillingService.get_billing_records(
            current_user.id, limit=limit, offset=offset
        )
        return {
            "data": [r.to_dict() for r in records],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@console_ns.route("/creator/admin/billing/records")
class AdminBillingRecordsApi(Resource):
    """List all billing records (super admin only)."""

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="管理员查看所有账单记录，可按工作空间或用户过滤（仅超级管理员可用）。",
        params={
            "limit": "每页条数，最大 100，默认 50",
            "offset": "偏移量，默认 0",
            "tenant_id": "可选，按工作空间过滤",
            "account_id": "可选，按用户过滤",
        },
        responses={
            200: ("成功", billing_record_list_resp),
            403: "无权限",
        },
    )
    @console_ns.marshal_with(billing_record_list_resp)
    def get(self):
        """管理员获取所有账单记录"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))
        tenant_id = request.args.get("tenant_id")
        account_id = request.args.get("account_id")

        records, total = UserBillingService.get_all_billing_records(
            tenant_id=tenant_id, account_id=account_id, limit=limit, offset=offset
        )
        return {
            "data": [r.to_dict() for r in records],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@console_ns.route("/creator/admin/topup/orders")
class AdminTopupOrdersApi(Resource):
    """List every top-up order across the platform (super admin only).

    Distinct from ``/workspaces/current/topup/orders`` which is owner-scoped to
    a single workspace. This endpoint lets operations staff see pending /
    closed / expired orders — not just the successful topups visible in the
    ``BillingRecord`` stream — so they can investigate stuck payments.
    """

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description=(
            "管理员查看平台所有充值订单（仅超级管理员可用）。"
            "包含 pending/success/failed/expired 等各状态订单，"
            "可按工作空间、用户或状态过滤，用于排查支付异常。"
        ),
        params={
            "limit": "每页条数，最大 100，默认 50",
            "offset": "偏移量，默认 0",
            "tenant_id": "可选，按工作空间过滤",
            "account_id": "可选，按用户过滤",
            "status": "可选，按订单状态过滤：pending / success / failed / expired",
        },
        responses={
            200: ("成功", topup_order_list_resp),
            403: "无权限",
        },
    )
    @console_ns.marshal_with(topup_order_list_resp)
    def get(self):
        """管理员获取所有充值订单"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        limit = min(int(request.args.get("limit", 50)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
        tenant_id = request.args.get("tenant_id") or None
        account_id = request.args.get("account_id") or None
        status = request.args.get("status") or None

        orders, total = PaymentService.from_config().list_platform_orders(
            tenant_id=tenant_id,
            account_id=account_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return {
            "data": [serialize_order(o) for o in orders],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
