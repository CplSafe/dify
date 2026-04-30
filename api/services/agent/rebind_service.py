"""RebindService — customer-initiated rebind, sysadmin-approved.

Lifecycle: pending → approved/rejected.

On approval: ``account_invitations.agent_id`` is flipped to the new agent.
``rebate_records.agent_id`` is NEVER changed by this flow — pre-rebind
earnings stay locked to the original agent. This is the CORE invariant
documented in design §5.4.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import and_, select

from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.agent import Agent, RebindRequest, RebindStatus
from models.creator import AccountInvitation
from services.errors.agent import (
    AgentNotFoundError,
    DuplicatePendingRebindError,
    RebindCooldownActiveError,
    RebindRequestNotFoundError,
)


COOLDOWN_DAYS = 90


class RebindService:
    """Manage rebind requests + sysadmin review."""

    @classmethod
    def create_request(
        cls, *, account_id: str, from_agent_id: str, to_agent_id: str,
    ) -> RebindRequest:
        """Stage a new pending rebind request. Caller commits."""
        for aid in (from_agent_id, to_agent_id):
            if db.session.scalar(select(Agent).where(Agent.id == aid)) is None:
                raise AgentNotFoundError(f"agent {aid} not found")

        existing_pending = db.session.scalar(
            select(RebindRequest).where(
                and_(
                    RebindRequest.account_id == account_id,
                    RebindRequest.status == RebindStatus.PENDING.value,
                )
            )
        )
        if existing_pending:
            raise DuplicatePendingRebindError(
                f"account {account_id} already has a pending rebind"
            )

        last_approved = db.session.scalar(
            select(RebindRequest)
            .where(
                and_(
                    RebindRequest.account_id == account_id,
                    RebindRequest.status == RebindStatus.APPROVED.value,
                )
            )
            .order_by(RebindRequest.reviewed_at.desc())
        )
        if last_approved is not None and last_approved.reviewed_at is not None:
            elapsed = naive_utc_now() - last_approved.reviewed_at
            if elapsed < timedelta(days=COOLDOWN_DAYS):
                remaining = COOLDOWN_DAYS - elapsed.days
                raise RebindCooldownActiveError(
                    f"cooldown active, {remaining} day(s) remaining"
                )

        req = RebindRequest(
            account_id=account_id,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
        )
        db.session.add(req)
        return req

    @classmethod
    def approve(
        cls, request_id: str, *,
        reviewer_id: str, note: Optional[str] = None,
    ) -> RebindRequest:
        """Approve rebind. Flips account_invitations.agent_id; never
        touches rebate_records.agent_id (the CORE invariant)."""
        req = db.session.scalar(
            select(RebindRequest).where(RebindRequest.id == request_id)
        )
        if req is None or req.status != RebindStatus.PENDING.value:
            raise RebindRequestNotFoundError(
                f"rebind request {request_id} not pending"
            )

        binding = db.session.scalar(
            select(AccountInvitation).where(
                and_(
                    AccountInvitation.invitee_account_id == req.account_id,
                    AccountInvitation.status == "used",
                )
            )
        )
        if binding is None:
            raise RebindRequestNotFoundError(
                f"invitee {req.account_id} has no active binding"
            )

        new_agent = db.session.scalar(
            select(Agent).where(Agent.id == req.to_agent_id)
        )
        if new_agent is None:
            # Defensive: create_request validated this, but the to_agent
            # could have been deleted between request and review.
            raise AgentNotFoundError(f"agent {req.to_agent_id} no longer exists")

        binding.agent_id = req.to_agent_id
        binding.inviter_account_id = new_agent.account_id

        req.status = RebindStatus.APPROVED.value
        req.reviewer_id = reviewer_id
        req.review_note = note
        req.reviewed_at = naive_utc_now()
        return req

    @classmethod
    def reject(
        cls, request_id: str, *,
        reviewer_id: str, note: Optional[str] = None,
    ) -> RebindRequest:
        req = db.session.scalar(
            select(RebindRequest).where(RebindRequest.id == request_id)
        )
        if req is None or req.status != RebindStatus.PENDING.value:
            raise RebindRequestNotFoundError(
                f"rebind request {request_id} not pending"
            )
        req.status = RebindStatus.REJECTED.value
        req.reviewer_id = reviewer_id
        req.review_note = note
        req.reviewed_at = naive_utc_now()
        return req
