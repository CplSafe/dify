"""Daily rebate settlement task.

Runs once per day (the celery beat schedule is built from
``RebateConfig.settlement_hour`` at worker boot time — see ext_celery).
Calculates rebates based on each invitee's **consumption** (deductions)
from the previous day, then writes a PENDING ``RebateRecord`` row tagged
with the invitee's authorised agent.

Filters non-agent invitations:
  Only invitees bound to an ACTIVE ``Agent`` row earn rebates. The
  ``agents`` JOIN is the database-layer enforcement of design §3.3 —
  upstream callers cannot bypass it.

The rebate is NOT credited to the agent's wallet here — the companion
task ``rebate_unfreeze_task`` moves funds from PENDING records into
``AgentWallet.withdrawable`` after ``RebateConfig.freeze_days`` elapse.
Operators can cancel a pending record during the freeze window to
reverse rebates tied to abusive invitees.

Formula:
  If cost_rate > 0:
    rebate = consumption * (1 - cost_rate/100) * rebate_rate/100
  Else:
    rebate = consumption * rebate_rate/100

Different models have different token prices, but deduction BillingRecords
already express the cost in CNY, so the amount is model-agnostic.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

import click
from celery import shared_task
from sqlalchemy import and_, func, select

from extensions.ext_database import db
from models.agent import Agent, AgentStatus
from models.creator import (
    AccountInvitation,
    BillingRecord,
    BillingRecordType,
    RebateConfig,
    RebateRecord,
    RebateRecordStatus,
)

logger = logging.getLogger(__name__)


@shared_task(queue="dataset")
def rebate_settlement_task():
    """Calculate and distribute rebates for the previous day's consumption."""
    click.echo(click.style("rebate_settlement_task: starting", fg="green"))

    # 1. Load config
    config = db.session.scalar(select(RebateConfig).limit(1))
    if not config or not config.is_enabled:
        click.echo("Rebate settlement is disabled or not configured. Skipping.")
        return

    rebate_rate = config.rebate_rate
    cost_rate = config.cost_rate
    if rebate_rate <= 0:
        click.echo("Rebate rate is 0. Skipping.")
        return

    # 2. Determine settlement date (yesterday)
    yesterday = (datetime.utcnow() - timedelta(days=1)).date()
    settlement_date_str = yesterday.isoformat()  # YYYY-MM-DD
    day_start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
    day_end = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)

    click.echo(f"Settlement date: {settlement_date_str}, rate: {rebate_rate}%, cost: {cost_rate}%")

    # 3. Find all invitees bound to ACTIVE agents.
    #
    # The JOIN against ``agents`` is the hard execution point of the
    # design's "only authorized agents earn rebates" rule (§3.3).
    # Suspended agents and orphan invitations (the agent was deleted)
    # are filtered out at the database layer — no upstream caller can
    # bypass it.
    used_invitations = db.session.scalars(
        select(AccountInvitation)
        .join(Agent, Agent.id == AccountInvitation.agent_id)
        .where(
            and_(
                AccountInvitation.status == "used",
                AccountInvitation.invitee_account_id.isnot(None),
                Agent.status == AgentStatus.ACTIVE.value,
            )
        )
    ).all()

    if not used_invitations:
        click.echo("No invitees bound to active agents. Nothing to settle.")
        return

    # Build invitee → invitation map. We keep the whole invitation row so
    # we can read both ``inviter_account_id`` (denormalised account) and
    # ``agent_id`` (the new locked-on-write reference) without a 2nd query.
    invitee_to_invitation: dict[str, AccountInvitation] = {
        inv.invitee_account_id: inv for inv in used_invitations
    }

    invitee_ids = list(invitee_to_invitation.keys())

    # 4. Aggregate yesterday's consumption (deductions) per invitee
    consumption_query = (
        select(
            BillingRecord.account_id,
            func.sum(func.abs(BillingRecord.amount)),
        )
        .where(
            and_(
                BillingRecord.account_id.in_(invitee_ids),
                BillingRecord.record_type == BillingRecordType.DEDUCTION,
                BillingRecord.created_at >= day_start,
                BillingRecord.created_at <= day_end,
            )
        )
        .group_by(BillingRecord.account_id)
    )

    consumption_rows = db.session.execute(consumption_query).all()
    if not consumption_rows:
        click.echo("No consumption found for invitees yesterday. Skipping.")
        return

    click.echo(f"Found consumption for {len(consumption_rows)} invitees.")

    # 5. Calculate and distribute rebates
    total_rebate_distributed = Decimal(0)
    records_created = 0

    for invitee_account_id, consumption_abs in consumption_rows:
        invitation = invitee_to_invitation.get(invitee_account_id)
        if invitation is None:
            continue
        inviter_account_id = invitation.inviter_account_id
        agent_id = invitation.agent_id

        consumption = Decimal(str(consumption_abs))
        if consumption <= 0:
            continue

        # Check for duplicate settlement
        existing = db.session.scalar(
            select(RebateRecord).where(
                and_(
                    RebateRecord.inviter_account_id == inviter_account_id,
                    RebateRecord.invitee_account_id == invitee_account_id,
                    RebateRecord.settlement_date == settlement_date_str,
                )
            )
        )
        if existing:
            logger.info(
                "Rebate already settled for inviter=%s invitee=%s date=%s, skipping.",
                inviter_account_id, invitee_account_id, settlement_date_str,
            )
            continue

        # Calculate rebate
        if cost_rate > 0:
            profit = consumption * (Decimal(1) - cost_rate / Decimal(100))
            rebate_amount = profit * rebate_rate / Decimal(100)
            cost_amount = consumption * cost_rate / Decimal(100)
        else:
            rebate_amount = consumption * rebate_rate / Decimal(100)
            cost_amount = Decimal(0)

        rebate_amount = rebate_amount.quantize(Decimal("0.000001"))
        cost_amount = cost_amount.quantize(Decimal("0.000001"))

        if rebate_amount <= 0:
            continue

        # 5a. Create RebateRecord in PENDING status.
        # ``agent_id`` is locked on write — subsequent rebinds NEVER
        # mutate this column, preserving the design §5.4 invariant
        # (pre-rebind earnings stay with the original agent).
        # No BillingRecord is written here: the ledger-visible cash event
        # happens at unfreeze time, when AgentWalletService.credit_settled
        # adds the amount to the agent's withdrawable balance.
        rebate_record = RebateRecord(
            inviter_account_id=inviter_account_id,
            agent_id=agent_id,
            invitee_account_id=invitee_account_id,
            settlement_date=settlement_date_str,
            consumption_amount=consumption,
            cost_amount=cost_amount,
            rebate_amount=rebate_amount,
            rebate_rate=rebate_rate,
            cost_rate=cost_rate,
            status=RebateRecordStatus.PENDING.value,
        )
        db.session.add(rebate_record)

        total_rebate_distributed += rebate_amount
        records_created += 1

    db.session.commit()
    click.echo(
        click.style(
            f"rebate_settlement_task: completed. "
            f"Settled {records_created} records, total rebate: {total_rebate_distributed} CNY",
            fg="green",
        )
    )
