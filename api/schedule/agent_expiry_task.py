"""Daily agent expiry task.

Scans for active agents whose ``expires_at`` is on or before today and
flips their status to ``suspended``. Runs once per day (early morning,
e.g. 00:30 UTC) so an agent's last day of authorisation is honoured in
full and they wake up suspended on the day after expiry.

Suspending an agent immediately:
- Stops further rebate accruals (``rebate_settlement_task`` JOINs against
  ``agents.status='active'``).
- Disables binding (``AgentInvitationService.bind`` rejects suspended).
- Blocks /agent/* console access (``@agent_required`` rejects suspended).

Existing PENDING ``RebateRecord`` rows are NOT cancelled — agents keep
the right to be paid out for already-earned rebates that are still in
the freeze window. Operators wanting to claw back earnings must do so
explicitly through the rebate cancellation flow.
"""

import logging
from datetime import date

import click
from celery import shared_task
from sqlalchemy import and_, select

from extensions.ext_database import db
from models.agent import Agent, AgentStatus

logger = logging.getLogger(__name__)


@shared_task(queue="dataset")
def agent_expiry_task():
    """Suspend agents whose expires_at <= today."""
    click.echo(click.style("agent_expiry_task: starting", fg="green"))

    today = date.today()
    expired = db.session.scalars(
        select(Agent).where(
            and_(
                Agent.expires_at.isnot(None),
                Agent.expires_at <= today,
                Agent.status == AgentStatus.ACTIVE.value,
            )
        )
    ).all()

    if not expired:
        click.echo("agent_expiry_task: no expired agents")
        return

    for agent in expired:
        agent.status = AgentStatus.SUSPENDED.value
        logger.info(
            "agent_expiry_task: suspended agent=%s expires_at=%s",
            agent.id,
            agent.expires_at,
        )

    db.session.commit()
    click.echo(
        click.style(
            f"agent_expiry_task: suspended {len(expired)} expired agent(s)",
            fg="green",
        )
    )
