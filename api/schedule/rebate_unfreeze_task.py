"""Daily rebate unfreeze task.

Companion to ``rebate_settlement_task``. The settlement task creates
PENDING ``RebateRecord`` rows tagged with the agent. This task releases
them into the agent's ``AgentWallet.withdrawable`` (and bumps
``total_earned``) once ``RebateConfig.freeze_days`` have elapsed.

Split between two tasks (rather than one) so operators get a cancellation
window: during ``freeze_days`` they can mark a ``RebateRecord`` as
``cancelled`` to claw back rebates tied to abusive invitees without
having to reverse an already-credited cash movement.

Ordering note: settlement and unfreeze must NOT run at the same hour —
running them concurrently on the same agent risks double-counting
(a fresh PENDING row could slip past the freeze cutoff before the
sweep finishes). Configured via ``RebateConfig.settlement_hour``.

Wallet wiring: all credits flow through ``AgentWalletService.credit_settled``
so wallet writes go through a single audit point.
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
    RebateConfig,
    RebateRecord,
    RebateRecordStatus,
)
from services.agent.agent_wallet_service import AgentWalletService

logger = logging.getLogger(__name__)


@shared_task(queue="dataset")
def rebate_unfreeze_task():
    """Release PENDING rebates whose freeze window has elapsed."""
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
        rebate_amount = Decimal(str(record.rebate_amount))
        if rebate_amount <= 0:
            # Defensive: a zero/negative pending rebate shouldn't exist, but
            # if it does, close it out without moving money.
            record.status = RebateRecordStatus.SETTLED.value
            record.unfrozen_at = now
            db.session.add(record)
            continue

        # Wallet credit goes through AgentWalletService — the single
        # auditable mutation point for AgentWallet rows.
        try:
            AgentWalletService.credit_settled(record.agent_id, rebate_amount)
        except ValueError:
            # The agent's wallet was deleted out-of-band. Leave the record
            # PENDING so a future sweep can retry once ops restores the
            # wallet (or cancels the record).
            logger.warning(
                "rebate_unfreeze_task: no AgentWallet for agent=%s record=%s — skipping",
                record.agent_id,
                record.id,
            )
            continue

        record.status = RebateRecordStatus.SETTLED.value
        record.unfrozen_at = now
        db.session.add(record)

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
