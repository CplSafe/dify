"""SQLAlchemy models for the agent system.

See docs/plans/2026-04-30-agent-system-design.md §2 for the data model.
"""
from __future__ import annotations

import enum
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import TypeBase
from .types import StringUUID


def _isoformat_utc(value: datetime | None) -> str | None:
    """Serialize database timestamps with an explicit UTC offset.

    PostgreSQL ``timestamp without time zone`` columns are populated with UTC
    values. SQLAlchemy returns them as naive ``datetime`` objects, so the API
    must attach ``+00:00``; otherwise browsers parse the string as local time
    and show an 8-hour shift for China Standard Time viewers.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


class AgentStatus(enum.StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class AgentLevel(enum.StrEnum):
    NATIONAL = "national"
    PROVINCE = "province"
    CITY = "city"


class RebindStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class WithdrawalStatus(enum.StrEnum):
    PENDING = "pending"
    PAID = "paid"
    REJECTED = "rejected"


class PayoutMethod(enum.StrEnum):
    ALIPAY = "alipay"
    WECHAT = "wechat"
    BANK = "bank"


class Agent(TypeBase):
    """Authorized referral agent. One per account, opened by sysadmin."""

    __tablename__ = "agents"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="agent_pkey"),
        sa.Index("agent_account_id_idx", "account_id", unique=True),
        sa.Index("agent_status_idx", "status"),
        sa.Index("agent_expires_at_idx", "expires_at"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()), init=False,
    )
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(StringUUID, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default=AgentStatus.ACTIVE.value,
        default=AgentStatus.ACTIVE.value,
    )
    rebate_rate: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(precision=5, scale=4), nullable=True, default=None,
    )
    level: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    region_province: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    region_city: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    signed_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True, default=None)
    expires_at: Mapped[date | None] = mapped_column(sa.Date, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
        onupdate=func.current_timestamp(),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "name": self.name,
            "status": self.status,
            "rebate_rate": str(self.rebate_rate) if self.rebate_rate is not None else None,
            "level": self.level,
            "region_province": self.region_province,
            "region_city": self.region_city,
            "contact_phone": self.contact_phone,
            "notes": self.notes,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_by": self.created_by,
            "created_at": _isoformat_utc(self.created_at),
            "updated_at": _isoformat_utc(self.updated_at),
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"


class AgentWallet(TypeBase):
    """1:1 wallet per agent. All earnings + withdrawals flow through here."""

    __tablename__ = "agent_wallets"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="agent_wallet_pkey"),
        sa.Index("agent_wallet_agent_id_idx", "agent_id", unique=True),
        sa.CheckConstraint("withdrawable >= 0", name="agent_wallet_withdrawable_nonneg"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()), init=False,
    )
    agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    withdrawable: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0),
    )
    total_earned: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0),
    )
    total_withdrawn: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
        onupdate=func.current_timestamp(),
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"


class RebindRequest(TypeBase):
    """Customer-initiated rebind to a different agent. Sysadmin-reviewed."""

    __tablename__ = "rebind_requests"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="rebind_request_pkey"),
        sa.Index("rebind_request_account_id_idx", "account_id"),
        sa.Index(
            "rebind_request_pending_unique_idx",
            "account_id",
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()), init=False,
    )
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    from_agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    to_agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default=RebindStatus.PENDING.value,
        default=RebindStatus.PENDING.value,
    )
    reviewer_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"


class WithdrawalRequest(TypeBase):
    """Agent-initiated withdrawal. Sysadmin marks paid after offline transfer."""

    __tablename__ = "withdrawal_requests"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="withdrawal_request_pkey"),
        sa.Index("withdrawal_request_agent_id_idx", "agent_id"),
        sa.Index(
            "withdrawal_request_pending_unique_idx",
            "agent_id",
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()), init=False,
    )
    agent_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), nullable=False,
    )
    payout_method: Mapped[str] = mapped_column(String(16), nullable=False)
    payout_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default=WithdrawalStatus.PENDING.value,
        default=WithdrawalStatus.PENDING.value,
    )
    reviewer_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"
