"""Daily rebate settlement task.

Runs once per day (the celery beat schedule is built from
``RebateConfig.settlement_hour`` at worker boot time — see ext_celery).
Calculates rebates based on each invitee's **consumption** (deductions)
from the previous day, then parks the rebate in the inviter's
``UserBalance.rebate_pending`` (frozen) bucket.

The rebate does NOT become spendable here — the companion task
``rebate_unfreeze_task`` moves funds from ``rebate_pending`` to ``balance``
after ``RebateConfig.freeze_days`` elapse. Operators can cancel a pending
record during the freeze window to reverse rebates tied to abusive
invitees.

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
from models.creator import (
    AccountInvitation,
    BillingRecord,
    BillingRecordType,
    RebateConfig,
    RebateRecord,
    RebateRecordStatus,
    UserBalance,
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

    # 3. Find all invitees (users who were invited by someone)
    used_invitations = db.session.scalars(
        select(AccountInvitation).where(
            AccountInvitation.status == "used"
        )
    ).all()

    if not used_invitations:
        click.echo("No invitees found. Nothing to settle.")
        return

    # Build invitee → inviter map
    invitee_to_inviter: dict[str, str] = {}
    for inv in used_invitations:
        if inv.invitee_account_id:
            invitee_to_inviter[inv.invitee_account_id] = inv.inviter_account_id

    invitee_ids = list(invitee_to_inviter.keys())

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
        inviter_account_id = invitee_to_inviter.get(invitee_account_id)
        if not inviter_account_id:
            continue

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
        # No BillingRecord is written here: the ledger-visible cash event
        # happens at unfreeze time. Writing it now would misrepresent a
        # frozen amount as spendable income and double-count if the
        # record is later cancelled.
        rebate_record = RebateRecord(
            inviter_account_id=inviter_account_id,
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

        # 5b. Park the rebate in the inviter's frozen bucket. The
        # spendable ``balance`` field is untouched — the unfreeze task
        # will move funds across after freeze_days.
        balance = db.session.scalar(
            select(UserBalance).where(UserBalance.account_id == inviter_account_id)
        )
        if balance:
            balance.rebate_pending = balance.rebate_pending + rebate_amount
        else:
            balance = UserBalance(
                account_id=inviter_account_id,
                rebate_pending=rebate_amount,
            )
            db.session.add(balance)

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
