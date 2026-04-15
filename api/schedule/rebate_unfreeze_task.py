"""Daily rebate unfreeze task.

Companion to ``rebate_settlement_task``. The settlement task parks rebates
in ``UserBalance.rebate_pending`` (frozen). This task releases them into
the spendable ``UserBalance.balance`` after ``RebateConfig.freeze_days``
have elapsed.

Split between two tasks (rather than one) so operators get a cancellation
window: during ``freeze_days`` they can mark a ``RebateRecord`` as
``cancelled`` to claw back rebates tied to abusive invitees without
having to reverse an already-credited cash movement.

Ordering note: the settlement task and this task must NOT run at the same
hour — running them at the same moment on the same inviter risks a
rebate_pending balance that has already been released by a previous
unfreeze sweep being re-released because the new settlement row slipped
in before the pending decrement. Configured via RebateConfig hours.
"""

import logging
from datetime import timedelta
from decimal import Decimal

import click
from celery import shared_task
from sqlalchemy import and_, select

from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.creator import (
    BillingRecord,
    BillingRecordType,
    RebateConfig,
    RebateRecord,
    RebateRecordStatus,
    UserBalance,
)

logger = logging.getLogger(__name__)


@shared_task(queue="dataset")
def rebate_unfreeze_task():
    """Release rebates whose freeze window has elapsed into spendable balance."""
    click.echo(click.style("rebate_unfreeze_task: starting", fg="green"))

    config = db.session.scalar(select(RebateConfig).limit(1))
    if not config or not config.is_enabled:
        click.echo("Rebate is disabled or not configured. Skipping unfreeze.")
        return

    freeze_days = int(config.freeze_days or 0)
    # A 0-day freeze is allowed — it turns into "release on the next tick",
    # which is still preferable to crediting directly in the settlement task
    # because it keeps the cancellation API functional for the short window.
    now = naive_utc_now()
    cutoff = now - timedelta(days=freeze_days)

    click.echo(f"Unfreeze cutoff: {cutoff.isoformat()} (freeze_days={freeze_days})")

    # Find pending records whose freeze window has elapsed. We scan by
    # created_at rather than by a dedicated "release_at" field because
    # freeze_days can change at runtime — keying off created_at makes
    # config tweaks retroactive without a separate migration.
    pending_records = db.session.scalars(
        select(RebateRecord).where(
            and_(
                RebateRecord.status == RebateRecordStatus.PENDING.value,
                RebateRecord.created_at <= cutoff,
            )
        )
    ).all()

    if not pending_records:
        click.echo("No rebate records ready to unfreeze. Skipping.")
        return

    released = 0
    total_released = Decimal(0)

    for record in pending_records:
        # Lock the balance row for the duration of the move so a concurrent
        # deduction/topup that also touches this inviter can't observe a
        # window where rebate_pending is decremented but balance isn't
        # yet incremented.
        balance = db.session.scalar(
            select(UserBalance)
            .where(UserBalance.account_id == record.inviter_account_id)
            .with_for_update()
        )
        if not balance:
            # Settlement only creates RebateRecord alongside UserBalance, so
            # this is only reachable if the row was deleted out-of-band.
            # Skip rather than explode — the record stays pending and will
            # be picked up on the next sweep (when presumably the balance
            # row has been restored or the record has been cancelled).
            logger.warning(
                "rebate_unfreeze_task: no UserBalance for inviter=%s record=%s — skipping",
                record.inviter_account_id,
                record.id,
            )
            continue

        rebate_amount = Decimal(str(record.rebate_amount))
        if rebate_amount <= 0:
            # Defensive: a zero/negative pending rebate shouldn't exist, but
            # if it does, close it out without moving money.
            record.status = RebateRecordStatus.SETTLED.value
            record.unfrozen_at = now
            db.session.add(record)
            continue

        # Guard against rebate_pending going negative. If the bucket has
        # been drained out-of-band (e.g. manual DB correction) we'd rather
        # log and skip than silently write a negative balance.
        if balance.rebate_pending < rebate_amount:
            logger.warning(
                "rebate_unfreeze_task: rebate_pending (%s) < record.rebate_amount (%s) "
                "for inviter=%s record=%s — skipping",
                balance.rebate_pending,
                rebate_amount,
                record.inviter_account_id,
                record.id,
            )
            continue

        balance.rebate_pending = balance.rebate_pending - rebate_amount
        balance.balance = balance.balance + rebate_amount

        record.status = RebateRecordStatus.SETTLED.value
        record.unfrozen_at = now
        db.session.add(record)

        # Write the ledger entry NOW (not at settlement time). Writing
        # here means a cancelled rebate leaves no ghost BillingRecord
        # behind, so the ledger always matches the actual cash movement.
        billing = BillingRecord(
            account_id=record.inviter_account_id,
            amount=rebate_amount,
            record_type=BillingRecordType.REBATE,
            description=f"邀请返点（被邀请人消费 {record.consumption_amount} CNY）",
        )
        db.session.add(billing)

        released += 1
        total_released += rebate_amount

    db.session.commit()
    click.echo(
        click.style(
            f"rebate_unfreeze_task: completed. "
            f"Released {released} records, total: {total_released} CNY",
            fg="green",
        )
    )
