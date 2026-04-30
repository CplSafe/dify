"""AgentDashboardService — aggregate queries for the agent console homepage.

All multi-row queries are written as single GROUP BY statements (not per-
invitee loops) to avoid N+1 cost — the dashboard runs on every page load.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, select

from extensions.ext_database import db
from models.agent import AgentWallet
from models.creator import (
    AccountInvitation,
    BillingRecord,
    BillingRecordType,
    RebateRecord,
    RebateRecordStatus,
)


class AgentDashboardService:
    """Read-only aggregation queries for the agent console homepage."""

    @classmethod
    def wallet_summary(cls, agent_id: str) -> dict:
        """Four wallet metrics: withdrawable / total_earned / total_withdrawn / pending.

        ``pending`` sums RebateRecord rows that are status='pending' and
        belong to this agent — the rebate is settled but still inside the
        freeze window.
        """
        wallet = db.session.scalar(
            select(AgentWallet).where(AgentWallet.agent_id == agent_id)
        )
        if wallet is None:
            raise ValueError(f"agent {agent_id} has no wallet")

        pending_total = db.session.scalar(
            select(func.coalesce(func.sum(RebateRecord.rebate_amount), 0)).where(
                and_(
                    RebateRecord.agent_id == agent_id,
                    RebateRecord.status == RebateRecordStatus.PENDING.value,
                )
            )
        ) or Decimal("0")

        return {
            "withdrawable": wallet.withdrawable,
            "total_earned": wallet.total_earned,
            "total_withdrawn": wallet.total_withdrawn,
            "pending": Decimal(str(pending_total)),
        }

    @classmethod
    def daily_consumption(cls, agent_id: str, *, days: int = 7) -> list[dict]:
        """Per-day consumption totals across all of this agent's invitees.

        Returns list ordered oldest → newest, length == ``days``. Empty
        days return 0 (NOT omitted).
        """
        if days <= 0:
            raise ValueError("days must be positive")

        today = date.today()
        start = today - timedelta(days=days - 1)

        invitee_ids = db.session.scalars(
            select(AccountInvitation.invitee_account_id).where(
                and_(
                    AccountInvitation.agent_id == agent_id,
                    AccountInvitation.status == "used",
                )
            )
        ).all()

        if not invitee_ids:
            return [
                {
                    "date": (start + timedelta(days=i)).isoformat(),
                    "consumption": Decimal("0"),
                }
                for i in range(days)
            ]

        # Single GROUP BY query — one row per day with non-zero consumption.
        rows = db.session.execute(
            select(
                func.date(BillingRecord.created_at).label("d"),
                func.sum(func.abs(BillingRecord.amount)).label("total"),
            ).where(
                and_(
                    BillingRecord.account_id.in_(invitee_ids),
                    BillingRecord.record_type == BillingRecordType.DEDUCTION,
                    BillingRecord.created_at >= datetime(start.year, start.month, start.day),
                )
            ).group_by(func.date(BillingRecord.created_at))
        ).all()

        by_date: dict[str, Decimal] = {}
        for row in rows:
            key = row.d.isoformat() if hasattr(row.d, "isoformat") else str(row.d)
            by_date[key] = Decimal(str(row.total))

        return [
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "consumption": by_date.get(
                    (start + timedelta(days=i)).isoformat(), Decimal("0"),
                ),
            }
            for i in range(days)
        ]

    @classmethod
    def invitees(cls, agent_id: str) -> list[dict]:
        """Per-invitee rollup row for the dashboard.

        One single query per metric (bindings + month consumption + lifetime
        rebate) — three queries total, never per-invitee.
        """
        today = date.today()
        month_start = date(today.year, today.month, 1)

        bindings = db.session.execute(
            select(
                AccountInvitation.invitee_account_id,
                AccountInvitation.used_at,
            ).where(
                and_(
                    AccountInvitation.agent_id == agent_id,
                    AccountInvitation.status == "used",
                )
            )
        ).all()

        if not bindings:
            return []

        invitee_ids = [b.invitee_account_id for b in bindings]

        month_consumption_rows = db.session.execute(
            select(
                BillingRecord.account_id,
                func.sum(func.abs(BillingRecord.amount)),
            ).where(
                and_(
                    BillingRecord.account_id.in_(invitee_ids),
                    BillingRecord.record_type == BillingRecordType.DEDUCTION,
                    BillingRecord.created_at >= datetime(
                        month_start.year, month_start.month, month_start.day,
                    ),
                )
            ).group_by(BillingRecord.account_id)
        ).all()
        month_consumption = {row[0]: Decimal(str(row[1])) for row in month_consumption_rows}

        lifetime_rows = db.session.execute(
            select(
                RebateRecord.invitee_account_id,
                func.sum(RebateRecord.rebate_amount),
            ).where(RebateRecord.agent_id == agent_id)
            .group_by(RebateRecord.invitee_account_id)
        ).all()
        lifetime_rebate = {row[0]: Decimal(str(row[1])) for row in lifetime_rows}

        return [
            {
                "invitee_account_id": b.invitee_account_id,
                "bound_at": b.used_at.isoformat() if b.used_at else None,
                "month_consumption": month_consumption.get(
                    b.invitee_account_id, Decimal("0"),
                ),
                "total_rebate": lifetime_rebate.get(
                    b.invitee_account_id, Decimal("0"),
                ),
            }
            for b in bindings
        ]
