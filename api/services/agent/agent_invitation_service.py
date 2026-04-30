"""AgentInvitationService — code generation + invitee binding.

Codes are long-lived and reusable: a single code may be bound by many
invitees over time. Each ``account_invitations`` row represents either:

- An *anchor* (``invitee_account_id IS NULL``) created at code-mint time.
  This row associates the code with its agent for fast lookup.
- A *binding* (``invitee_account_id IS NOT NULL``, ``status='used'``)
  created when an invitee confirms the bind.
"""
from __future__ import annotations

import secrets

from sqlalchemy import select

from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.agent import Agent, AgentStatus
from models.creator import AccountInvitation
from services.errors.agent import (
    AgentNotFoundError,
    AgentSuspendedError,
    AlreadyBoundError,
    InvalidAgentInvitationCodeError,
    SelfBindError,
)


_CODE_LENGTH = 16  # urlsafe-base64 characters


class AgentInvitationService:
    """Generate codes (called by agent) and bind codes (called by invitee)."""

    @classmethod
    def generate_invitation_code(cls, agent_id: str) -> str:
        """Mint a fresh long-lived invitation code for the given agent.

        Stages an anchor row in ``account_invitations`` so binds can later
        look up the agent by code without a separate lookup table. Caller
        commits the transaction.

        Raises:
            AgentNotFoundError: agent_id does not exist
        """
        agent = db.session.scalar(select(Agent).where(Agent.id == agent_id))
        if agent is None:
            raise AgentNotFoundError(f"agent {agent_id} not found")

        # Loop until we land on a fresh code. The 16-char urlsafe token has
        # ~96 bits of entropy so collisions are negligible, but the loop
        # makes the rare case explicit instead of relying on a unique-violation
        # exception path.
        code: str
        while True:
            code = secrets.token_urlsafe(_CODE_LENGTH)[:_CODE_LENGTH]
            collision = db.session.scalar(
                select(AccountInvitation).where(AccountInvitation.invite_code == code)
            )
            if collision is None:
                break

        anchor = AccountInvitation(
            invite_code=code,
            inviter_account_id=agent.account_id,
            agent_id=agent.id,
            invitee_account_id=None,
            status="pending",
        )
        db.session.add(anchor)
        return code

    @classmethod
    def bind(cls, *, invite_code: str, invitee_account_id: str) -> Agent:
        """Bind ``invitee_account_id`` to the agent behind ``invite_code``.

        Caller commits the transaction.

        Raises:
            InvalidAgentInvitationCodeError: empty code or no anchor
            AgentSuspendedError: agent is not active
            SelfBindError: invitee is the agent themselves
            AlreadyBoundError: invitee already bound to any agent
        """
        code = (invite_code or "").strip()
        if not code:
            raise InvalidAgentInvitationCodeError("empty code")

        anchor = db.session.scalar(
            select(AccountInvitation).where(
                AccountInvitation.invite_code == code,
                AccountInvitation.invitee_account_id.is_(None),
            )
        )
        if anchor is None:
            raise InvalidAgentInvitationCodeError(f"code {code} not found")

        agent = db.session.scalar(select(Agent).where(Agent.id == anchor.agent_id))
        if agent is None:
            raise InvalidAgentInvitationCodeError("orphan invitation anchor")
        if agent.status != AgentStatus.ACTIVE.value:
            raise AgentSuspendedError(f"agent {agent.id} is suspended")
        if agent.account_id == invitee_account_id:
            raise SelfBindError("an agent cannot bind to themselves")

        existing_binding = db.session.scalar(
            select(AccountInvitation).where(
                AccountInvitation.invitee_account_id == invitee_account_id,
                AccountInvitation.status == "used",
            )
        )
        if existing_binding:
            raise AlreadyBoundError(
                f"invitee {invitee_account_id} already bound to agent "
                f"{existing_binding.agent_id}"
            )

        binding = AccountInvitation(
            invite_code=code,
            inviter_account_id=agent.account_id,
            agent_id=agent.id,
            invitee_account_id=invitee_account_id,
            status="used",
            used_at=naive_utc_now(),
        )
        db.session.add(binding)
        return agent
