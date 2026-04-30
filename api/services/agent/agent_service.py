"""AgentService — sysadmin-facing agent CRUD.

The service stages mutations on the session but does NOT commit; callers
own the transaction boundary. This matches the project convention used
elsewhere (see ``services.user_billing_service``).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select

from extensions.ext_database import db
from models.agent import Agent, AgentStatus, AgentWallet
from services.errors.agent import (
    AgentAccountAlreadyExistsError,
    AgentNotFoundError,
)


_UPDATABLE_FIELDS = frozenset({
    "name",
    "rebate_rate",
    "level",
    "region_province",
    "region_city",
    "contact_phone",
    "notes",
    "signed_at",
    "expires_at",
})


class AgentService:
    """Manage agent lifecycle (create / suspend / update)."""

    @classmethod
    def create_agent(
        cls,
        *,
        account_id: str,
        name: str,
        created_by: str,
        rebate_rate: Optional[Decimal] = None,
        level: Optional[str] = None,
        region_province: Optional[str] = None,
        region_city: Optional[str] = None,
        contact_phone: Optional[str] = None,
        notes: Optional[str] = None,
        signed_at: Optional[date] = None,
        expires_at: Optional[date] = None,
    ) -> Agent:
        """Stage a new Agent + AgentWallet pair on the session.

        Raises:
            AgentAccountAlreadyExistsError: account_id is already an agent
        """
        existing = db.session.scalar(select(Agent).where(Agent.account_id == account_id))
        if existing:
            raise AgentAccountAlreadyExistsError(
                f"account {account_id} is already an agent"
            )

        agent = Agent(
            account_id=account_id,
            name=name,
            created_by=created_by,
            rebate_rate=rebate_rate,
            level=level,
            region_province=region_province,
            region_city=region_city,
            contact_phone=contact_phone,
            notes=notes,
            signed_at=signed_at,
            expires_at=expires_at,
        )
        db.session.add(agent)
        db.session.flush()  # populate agent.id so wallet can reference it

        wallet = AgentWallet(agent_id=agent.id)
        db.session.add(wallet)
        return agent

    @classmethod
    def get_by_id(cls, agent_id: str) -> Agent:
        agent = db.session.scalar(select(Agent).where(Agent.id == agent_id))
        if agent is None:
            raise AgentNotFoundError(f"agent {agent_id} not found")
        return agent

    @classmethod
    def get_by_account_id(cls, account_id: str) -> Optional[Agent]:
        return db.session.scalar(select(Agent).where(Agent.account_id == account_id))

    @classmethod
    def suspend_agent(cls, agent_id: str) -> Agent:
        """Mark agent as suspended. Their invite codes stop working immediately."""
        agent = cls.get_by_id(agent_id)
        agent.status = AgentStatus.SUSPENDED.value
        return agent

    @classmethod
    def update_agent(cls, agent_id: str, **fields: object) -> Agent:
        """Patch agent fields. Only whitelisted fields are accepted."""
        agent = cls.get_by_id(agent_id)
        for key, value in fields.items():
            if key not in _UPDATABLE_FIELDS:
                raise ValueError(f"field {key!r} is not updatable")
            setattr(agent, key, value)
        return agent
