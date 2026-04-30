"""Sysadmin read-only overviews.

Routes (under /console/api):

- GET /admin/rebate-records           paginated rebate ledger, filter by agent / date
- GET /admin/agent-consumption        per-agent rollup (invitee count, lifetime rebate, last 30d consumption)

These pages give operators visibility into the rebate ledger + agent
performance. Both are pure read paths — no mutations.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import request
from flask_restx import Resource
from sqlalchemy import and_, func, select
from werkzeug.exceptions import BadRequest

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
    system_admin_required,
)
from extensions.ext_database import db
from libs.login import login_required
from models.agent import Agent, AgentWallet
from models.creator import (
    AccountInvitation,
    BillingRecord,
    BillingRecordType,
    RebateRecord,
)


def _parse_iso_date(raw: str | None, field: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise BadRequest(f"invalid {field}: {raw!r}") from exc


def _serialize_rebate_record(r: RebateRecord) -> dict:
    return {
        "id": r.id,
        "inviter_account_id": r.inviter_account_id,
        "agent_id": r.agent_id,
        "invitee_account_id": r.invitee_account_id,
        "settlement_date": r.settlement_date,
        "consumption_amount": str(r.consumption_amount),
        "rebate_amount": str(r.rebate_amount),
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@console_ns.route("/admin/rebate-records")
class AdminRebateRecordsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def get(self) -> dict:
        page = max(1, int(request.args.get("page", 1)))
        limit = min(200, max(1, int(request.args.get("limit", 50))))
        agent_id = request.args.get("agent_id")
        from_date = _parse_iso_date(request.args.get("from"), "from")
        to_date = _parse_iso_date(request.args.get("to"), "to")

        stmt = select(RebateRecord).order_by(RebateRecord.settlement_date.desc())
        if agent_id:
            stmt = stmt.where(RebateRecord.agent_id == agent_id)
        if from_date:
            stmt = stmt.where(RebateRecord.settlement_date >= from_date.isoformat())
        if to_date:
            stmt = stmt.where(RebateRecord.settlement_date <= to_date.isoformat())

        offset = (page - 1) * limit
        rows = db.session.scalars(stmt.offset(offset).limit(limit)).all()
        return {
            "data": [_serialize_rebate_record(r) for r in rows],
            "page": page,
            "limit": limit,
            "has_more": len(rows) == limit,
        }


@console_ns.route("/admin/agent-consumption")
class AdminAgentConsumptionApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def get(self) -> dict:
        """Per-agent rollup for the consumption dashboard.

        Three aggregated queries (one per metric) joined in Python by
        agent_id — never per-agent fan-out. Bounded by ``Agent`` table
        size which is small (operator-curated list).
        """
        today = date.today()
        thirty_days_ago = datetime(today.year, today.month, today.day) - timedelta(days=30)

        agents = db.session.scalars(select(Agent).order_by(Agent.created_at.desc())).all()
        if not agents:
            return {"data": []}
        agent_ids = [a.id for a in agents]

        # Wallet (lifetime earned + withdrawn)
        wallet_rows = db.session.execute(
            select(
                AgentWallet.agent_id,
                AgentWallet.total_earned,
                AgentWallet.total_withdrawn,
                AgentWallet.withdrawable,
            ).where(AgentWallet.agent_id.in_(agent_ids))
        ).all()
        wallets = {row[0]: row for row in wallet_rows}

        # Invitee counts per agent
        invitee_rows = db.session.execute(
            select(
                AccountInvitation.agent_id,
                func.count(AccountInvitation.invitee_account_id),
            ).where(
                and_(
                    AccountInvitation.agent_id.in_(agent_ids),
                    AccountInvitation.status == "used",
                )
            ).group_by(AccountInvitation.agent_id)
        ).all()
        invitee_counts = {row[0]: int(row[1]) for row in invitee_rows}

        # Last-30d consumption: sum BillingRecord deductions for invitees of each agent.
        # JOIN bindings → billing records, GROUP BY agent_id.
        cons_rows = db.session.execute(
            select(
                AccountInvitation.agent_id,
                func.sum(func.abs(BillingRecord.amount)),
            ).join(
                BillingRecord,
                BillingRecord.account_id == AccountInvitation.invitee_account_id,
            ).where(
                and_(
                    AccountInvitation.agent_id.in_(agent_ids),
                    AccountInvitation.status == "used",
                    BillingRecord.record_type == BillingRecordType.DEDUCTION,
                    BillingRecord.created_at >= thirty_days_ago,
                )
            ).group_by(AccountInvitation.agent_id)
        ).all()
        last_30d = {row[0]: Decimal(str(row[1])) for row in cons_rows}

        return {
            "data": [
                {
                    "agent_id": a.id,
                    "name": a.name,
                    "status": a.status,
                    "level": a.level,
                    "region_province": a.region_province,
                    "region_city": a.region_city,
                    "invitee_count": invitee_counts.get(a.id, 0),
                    "withdrawable": str(wallets.get(a.id, (None, 0, 0, 0))[3]) if a.id in wallets else "0",
                    "total_earned": str(wallets.get(a.id, (None, 0, 0, 0))[1]) if a.id in wallets else "0",
                    "total_withdrawn": str(wallets.get(a.id, (None, 0, 0, 0))[2]) if a.id in wallets else "0",
                    "last_30d_consumption": str(last_30d.get(a.id, Decimal("0"))),
                }
                for a in agents
            ],
        }
