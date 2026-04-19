"""Workspace allocation endpoints (owner only).

Exposes the tenant->member fund-transfer ledger:

- POST /workspaces/current/members/<member_id>/allocations — allocate or
  reclaim funds (signed ``amount`` in yuan). Positive amounts move funds
  tenant -> member; negative amounts reclaim member -> tenant.
- GET /workspaces/current/allocations — paginated audit list for the
  workspace (newest first).

All mutation endpoints require the workspace OWNER role via
``@tenant_owner_required``; the list endpoint is owner-only as well,
since allocation history exposes per-member spend patterns.

Amount contract: the service layer works in ``Decimal`` yuan. The HTTP
layer accepts yuan as a decimal string or number to keep parity with the
``TenantBalance`` / ``UserBalance`` responses (which serialise to
strings). This mirrors the existing wallet payloads and avoids a second
fen/yuan contract in the console API.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import request
from flask_restx import Resource, fields
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
    tenant_owner_required,
)
from libs.exception import BaseHTTPException
from libs.login import current_account_with_tenant, login_required
from models.account import Account, TenantAccountJoin
from models.creator import UserBalance
from models.engine import db
from services.wallet.allocation_service import AllocationService
from services.wallet.exceptions import (
    AllocateToOwnerNotAllowed,
    InsufficientMemberBalance,
    InsufficientTenantBalance,
    NotTenantMember,
)

# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class AllocationAmountInvalidError(BaseHTTPException):
    error_code = "allocation_amount_invalid"
    description = "Allocation amount is invalid."
    code = 400


class AllocationMemberNotFoundError(BaseHTTPException):
    error_code = "allocation_member_not_found"
    description = "Target account is not a member of this workspace."
    code = 404


class AllocationInsufficientTenantBalanceError(BaseHTTPException):
    error_code = "allocation_insufficient_tenant_balance"
    description = "Workspace wallet has insufficient balance for this allocation."
    code = 409


class AllocationInsufficientMemberBalanceError(BaseHTTPException):
    error_code = "allocation_insufficient_member_balance"
    description = "Member wallet has insufficient balance for this reclaim."
    code = 409


class AllocationToOwnerNotAllowedError(BaseHTTPException):
    error_code = "allocation_to_owner_not_allowed"
    description = (
        "Cannot allocate to or reclaim from the workspace owner; "
        "owners draw funds directly from the workspace wallet."
    )
    code = 409


# ---------------------------------------------------------------------------
# Swagger 模型定义（模块级，避免重复注册）
# ---------------------------------------------------------------------------

allocation_create_req = console_ns.model(
    "AllocationCreateReq",
    {
        "amount": fields.String(
            required=True,
            description="签名金额（元），正数为分配，负数为追回",
            example="100.00",
        ),
        "description": fields.String(
            required=False,
            description="备注说明，最多 256 个字符（可为空）",
            example="季度额度充值",
        ),
    },
)

allocation_item = console_ns.model(
    "AllocationItem",
    {
        "id": fields.String(description="分配记录 ID"),
        "tenant_id": fields.String(description="工作空间 ID"),
        "account_id": fields.String(description="目标成员账号 ID"),
        "operator_id": fields.String(description="操作人账号 ID（工作空间所有者）"),
        "amount": fields.String(description="分配金额（元），负数为追回"),
        "description": fields.String(description="备注说明"),
        "created_at": fields.String(description="操作时间 ISO8601"),
    },
)

allocation_list_resp = console_ns.model(
    "AllocationListResp",
    {
        "data": fields.List(fields.Nested(allocation_item), description="分配记录列表"),
        "total": fields.Integer(description="总记录数"),
        "limit": fields.Integer(description="每页条数"),
        "offset": fields.Integer(description="偏移量"),
    },
)

member_balance_item = console_ns.model(
    "MemberBalanceItem",
    {
        "account_id": fields.String(description="成员账号 ID"),
        "balance": fields.String(description="当前余额（元）"),
        "currency": fields.String(description="货币单位，默认 CNY"),
    },
)

member_balances_resp = console_ns.model(
    "MemberBalancesResp",
    {
        "data": fields.List(fields.Nested(member_balance_item), description="成员余额列表"),
    },
)

# ---------------------------------------------------------------------------
# Request payload
# ---------------------------------------------------------------------------


class CreateAllocationPayload(BaseModel):
    """Allocation request body.

    ``amount`` is a signed decimal yuan value. Positive = allocate,
    negative = reclaim. Zero is rejected by the service layer.

    ``description`` is optional free text kept for the audit trail
    (shown in the tenant billing history).
    """

    model_config = ConfigDict(strict=False)  # allow "1.23" strings

    amount: Decimal = Field(..., description="Signed yuan amount; positive=allocate, negative=reclaim")
    description: str | None = Field(default=None, max_length=256)

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, v):
        """Accept int/float/str; reject things that can't become Decimal."""
        if v is None or v == "":
            raise ValueError("amount is required")
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"amount is not a valid decimal: {v}") from e


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


def _allocation_payload(record) -> dict:
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "account_id": record.account_id,
        "operator_id": record.operator_id,
        "amount": str(record.amount),
        "description": record.description,
        "created_at": record.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@console_ns.route("/workspaces/current/members/<string:member_id>/allocations")
class MemberAllocationApi(Resource):
    """Allocate or reclaim funds for a specific workspace member."""

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    @console_ns.doc(
        description="工作空间所有者向指定成员分配或追回额度（正数为分配，负数为追回）",
        responses={
            201: ("分配成功，返回分配记录", allocation_item),
            400: "金额参数无效（格式错误或为零）",
            401: "未登录",
            403: "仅工作空间所有者可操作",
            404: "目标成员不存在于当前工作空间",
            409: "余额不足或不允许对所有者进行分配",
        },
    )
    @console_ns.expect(allocation_create_req, validate=False)
    def post(self, member_id: str):
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            payload = CreateAllocationPayload.model_validate(request.get_json() or {})
        except ValidationError as e:
            raise AllocationAmountInvalidError(str(e))

        try:
            record = AllocationService.allocate(
                tenant_id=current_tenant_id,
                account_id=member_id,
                operator_id=current_user.id,
                amount=payload.amount,
                description=payload.description,
            )
        except ValueError as e:
            # Zero amount, etc.
            raise AllocationAmountInvalidError(str(e))
        except NotTenantMember:
            raise AllocationMemberNotFoundError()
        except AllocateToOwnerNotAllowed:
            raise AllocationToOwnerNotAllowedError()
        except InsufficientTenantBalance:
            raise AllocationInsufficientTenantBalanceError()
        except InsufficientMemberBalance:
            raise AllocationInsufficientMemberBalanceError()

        return _allocation_payload(record), 201


@console_ns.route("/workspaces/current/allocations")
class TenantAllocationListApi(Resource):
    """List allocation history for the current workspace (owner only)."""

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    @console_ns.doc(
        description="获取当前工作空间的额度分配历史（仅所有者可查看，按时间倒序）",
        params={
            "limit": "每页条数，最大 100，默认 20",
            "offset": "分页偏移量，默认 0",
        },
        responses={
            200: ("成功", allocation_list_resp),
            401: "未登录",
            403: "仅工作空间所有者可操作",
        },
    )
    @console_ns.marshal_with(allocation_list_resp)
    def get(self):
        _, current_tenant_id = current_account_with_tenant()
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
        records, total = AllocationService.list_tenant_allocations(
            tenant_id=current_tenant_id,
            limit=limit,
            offset=offset,
        )
        return {
            "data": [_allocation_payload(r) for r in records],
            "total": total,
            "limit": limit,
            "offset": offset,
        }, 200


@console_ns.route("/workspaces/current/members/balances")
class MemberBalancesApi(Resource):
    """Return current wallet balances for every member of the workspace.

    Owner-only: the allocation UI needs this to show "member X has ¥Y
    left" before deciding how much to top up or claw back. System admins
    are excluded for the same reason as ``get_tenant_members`` — they
    are joined to every tenant for ops access, not as real members.

    Response shape mirrors the ``UserBalance`` fragment returned by the
    wallet endpoint (balance as decimal string) so the console never
    has to switch contracts mid-flow.
    """

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    @console_ns.doc(
        description="获取当前工作空间所有成员的钱包余额（仅所有者可查看，系统管理员账号不在列表中）",
        responses={
            200: ("成功", member_balances_resp),
            401: "未登录",
            403: "仅工作空间所有者可操作",
        },
    )
    @console_ns.marshal_with(member_balances_resp)
    def get(self):
        _, current_tenant_id = current_account_with_tenant()

        # Left outer join — a member without a UserBalance row yet still
        # appears, rendered as ¥0 by the service contract (balance rows
        # are lazily created on first topup/allocation).
        rows = db.session.execute(
            select(Account.id, UserBalance.balance, UserBalance.currency)
            .select_from(TenantAccountJoin)
            .join(Account, Account.id == TenantAccountJoin.account_id)
            .join(UserBalance, UserBalance.account_id == Account.id, isouter=True)
            .where(TenantAccountJoin.tenant_id == current_tenant_id)
            .where(Account.is_system_admin.is_(False))
        ).all()

        return {
            "data": [
                {
                    "account_id": account_id,
                    "balance": str(balance) if balance is not None else "0",
                    "currency": currency or "CNY",
                }
                for account_id, balance, currency in rows
            ],
        }, 200
