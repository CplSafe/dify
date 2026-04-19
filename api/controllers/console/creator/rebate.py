"""Rebate configuration & billing endpoints.

Super admin:
  GET  /creator/admin/rebate/config    — get current rebate config
  PUT  /creator/admin/rebate/config    — update rebate config (rate, cost, etc.)

All authenticated users (workspace owners):
  GET  /creator/rebate/records         — my rebate income records (paginated)
  GET  /creator/rebate/summary         — my total rebate income summary
"""

from decimal import Decimal, InvalidOperation

from flask import request
from flask_restx import Resource
from sqlalchemy import and_, func, select
from werkzeug.exceptions import BadRequest, Forbidden

from controllers.console import console_ns
from controllers.console.creator.models import (
    rebate_config_resp,
    rebate_config_update_req,
    rebate_record_list_resp,
    rebate_summary_resp,
)
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
    tenant_owner_required,
)
from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from libs.login import current_account_with_tenant, login_required
from models.creator import RebateConfig, RebateRecord, RebateRecordStatus, UserBalance


def _require_system_admin(user):
    if not user.is_system_admin:
        raise Forbidden("Only system administrators can perform this action")


def _get_or_create_config() -> RebateConfig:
    """Return the singleton rebate config, creating a default if none exists."""
    config = db.session.scalar(select(RebateConfig).limit(1))
    if not config:
        config = RebateConfig()
        db.session.add(config)
        db.session.commit()
    return config


# ---------------------------------------------------------------------------
# Super admin: rebate configuration
# ---------------------------------------------------------------------------


@console_ns.route("/creator/admin/rebate/config")
class RebateConfigApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="获取当前返佣配置（仅超级管理员可用）。配置不存在时自动创建默认配置。",
        responses={
            200: ("成功", rebate_config_resp),
            403: "无权限",
        },
    )
    @console_ns.marshal_with(rebate_config_resp)
    def get(self):
        """获取返佣配置"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        config = _get_or_create_config()
        return config.to_dict()

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description=(
            "更新返佣配置（仅超级管理员可用）。所有字段均为可选，"
            "仅传入需修改的字段即可。rebate_rate/cost_rate 范围 0-100，"
            "settlement_hour 范围 0-23，freeze_days 范围 0-90。"
        ),
        responses={
            200: ("成功", rebate_config_resp),
            400: "参数格式错误或超出范围",
            403: "无权限",
        },
    )
    @console_ns.expect(rebate_config_update_req, validate=False)
    @console_ns.marshal_with(rebate_config_resp)
    def put(self):
        """更新返佣配置"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        payload = request.get_json() or {}
        config = _get_or_create_config()

        if "rebate_rate" in payload:
            try:
                rate = Decimal(str(payload["rebate_rate"]))
            except (InvalidOperation, ValueError):
                raise BadRequest("rebate_rate must be a valid number")
            if rate < 0 or rate > 100:
                raise BadRequest("rebate_rate must be between 0 and 100")
            config.rebate_rate = rate

        if "cost_rate" in payload:
            try:
                cost = Decimal(str(payload["cost_rate"]))
            except (InvalidOperation, ValueError):
                raise BadRequest("cost_rate must be a valid number")
            if cost < 0 or cost > 100:
                raise BadRequest("cost_rate must be between 0 and 100")
            config.cost_rate = cost

        if "settlement_hour" in payload:
            hour = payload["settlement_hour"]
            if not isinstance(hour, int) or hour < 0 or hour > 23:
                raise BadRequest("settlement_hour must be an integer between 0 and 23")
            config.settlement_hour = hour

        if "freeze_days" in payload:
            days = payload["freeze_days"]
            # 0 = release on next unfreeze tick (kept legal for ops flexibility).
            # Upper bound is arbitrary-but-sane: beyond 90 days pending rebates
            # accumulate indefinitely and become an ops footgun.
            if not isinstance(days, int) or days < 0 or days > 90:
                raise BadRequest("freeze_days must be an integer between 0 and 90")
            config.freeze_days = days

        if "is_enabled" in payload:
            config.is_enabled = bool(payload["is_enabled"])

        config.updated_by = current_user.id
        db.session.commit()

        return config.to_dict()


@console_ns.route("/creator/admin/rebate/records/<string:record_id>/cancel")
class RebateRecordCancelApi(Resource):
    """Let a super admin claw back a still-pending rebate.

    Works by debiting the inviter's ``rebate_pending`` bucket and marking
    the record ``cancelled`` — only valid while the rebate is still frozen.
    Once the unfreeze task has moved the money to spendable ``balance``,
    the record is already ``settled`` and this endpoint rejects: clawing
    back spent money needs a separate manual adjustment.
    """

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description=(
            "管理员取消指定返佣记录（仅超级管理员可用）。"
            "只能取消状态为 pending（冻结中）的记录；"
            "已 settled 的记录需走人工调账。"
        ),
        responses={
            200: "取消成功，返回已更新的返佣记录",
            400: "记录不存在或状态不为 pending",
            403: "无权限",
        },
    )
    def post(self, record_id: str):
        """取消返佣记录"""
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        # Lock the record row: two concurrent cancel clicks would otherwise
        # both observe ``status == pending`` and both try to debit
        # rebate_pending, over-subtracting the amount.
        record = db.session.scalar(
            select(RebateRecord)
            .where(RebateRecord.id == record_id)
            .with_for_update()
        )
        if not record:
            raise BadRequest("Rebate record not found")
        if record.status != RebateRecordStatus.PENDING.value:
            raise BadRequest(
                f"Rebate record is not pending (status={record.status}); cannot cancel"
            )

        balance = db.session.scalar(
            select(UserBalance)
            .where(UserBalance.account_id == record.inviter_account_id)
            .with_for_update()
        )
        rebate_amount = Decimal(str(record.rebate_amount))
        if balance and balance.rebate_pending >= rebate_amount:
            balance.rebate_pending = balance.rebate_pending - rebate_amount
        # If balance is missing or rebate_pending already drained, we still
        # mark the record cancelled so it can't be swept by unfreeze — a
        # stuck pending row is worse than a minor ledger mismatch, which an
        # operator can reconcile manually from the audit log.

        record.status = RebateRecordStatus.CANCELLED.value
        record.unfrozen_at = naive_utc_now()
        db.session.add(record)
        db.session.commit()

        return record.to_dict()


# ---------------------------------------------------------------------------
# User: my rebate records & summary
# ---------------------------------------------------------------------------


@console_ns.route("/creator/rebate/records")
class RebateRecordListApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    @console_ns.doc(
        description="获取当前用户（邀请人）的返佣收入记录，分页返回，支持按日期过滤。仅工作空间 Owner 可访问。",
        params={
            "page": "页码，默认 1",
            "per_page": "每页条数，最大 100，默认 20",
            "date_from": "可选，起始日期（含），格式 YYYY-MM-DD",
            "date_to": "可选，截止日期（含），格式 YYYY-MM-DD",
        },
        responses={
            200: ("成功", rebate_record_list_resp),
            401: "未登录",
            403: "非 Owner 身份",
        },
    )
    @console_ns.marshal_with(rebate_record_list_resp)
    def get(self):
        """获取当前用户的返佣收入记录"""
        current_user, _ = current_account_with_tenant()
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 20)), 100)

        base_query = select(RebateRecord).where(
            RebateRecord.inviter_account_id == current_user.id
        )

        # Optional date filtering
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        if date_from:
            base_query = base_query.where(RebateRecord.settlement_date >= date_from)
        if date_to:
            base_query = base_query.where(RebateRecord.settlement_date <= date_to)

        total = db.session.scalar(
            select(func.count()).select_from(base_query.subquery())
        )

        records = db.session.scalars(
            base_query
            .order_by(RebateRecord.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()

        # Batch-load invitee names
        from models.account import Account
        invitee_ids = list({r.invitee_account_id for r in records})
        invitee_map: dict[str, str] = {}
        if invitee_ids:
            accounts = db.session.scalars(
                select(Account).where(Account.id.in_(invitee_ids))
            ).all()
            invitee_map = {a.id: a.name for a in accounts}

        result = []
        for r in records:
            d = r.to_dict()
            d["invitee_name"] = invitee_map.get(r.invitee_account_id, "")
            result.append(d)

        return {
            "data": result,
            "total": total,
            "page": page,
            "per_page": per_page,
        }


@console_ns.route("/creator/rebate/summary")
class RebateSummaryApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required
    @console_ns.doc(
        description="获取当前用户的返佣汇总统计，包括累计返佣总额、被邀请人消费总额、邀请人数。仅 Owner 可访问。",
        responses={
            200: ("成功", rebate_summary_resp),
            401: "未登录",
            403: "非 Owner 身份",
        },
    )
    @console_ns.marshal_with(rebate_summary_resp)
    def get(self):
        """获取当前用户的返佣汇总统计"""
        current_user, _ = current_account_with_tenant()

        # Total rebate earned
        total_rebate = db.session.scalar(
            select(func.coalesce(func.sum(RebateRecord.rebate_amount), 0)).where(
                RebateRecord.inviter_account_id == current_user.id
            )
        )

        # Count of invitees (distinct used invitations)
        from models.creator import AccountInvitation
        invitee_count = db.session.scalar(
            select(func.count()).where(
                and_(
                    AccountInvitation.inviter_account_id == current_user.id,
                    AccountInvitation.status == "used",
                )
            )
        )

        # Total consumption from all invitees
        total_consumption = db.session.scalar(
            select(func.coalesce(func.sum(RebateRecord.consumption_amount), 0)).where(
                RebateRecord.inviter_account_id == current_user.id
            )
        )

        return {
            "total_rebate": str(total_rebate),
            "total_consumption": str(total_consumption),
            "invitee_count": invitee_count,
            "currency": "CNY",
        }
