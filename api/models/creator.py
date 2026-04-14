"""Creator platform models.

Includes:
- UserBalance: per-account credit balance
- BillingRecord: deduction/topup history
- MarketplaceApp: workflow apps published to the marketplace
- UserGlobalApiKey: user-level API key that overrides per-app keys
- CreatorWork: generated content (videos, etc.) from workflow runs
- AccountInvitation: invitation code & parent-child referral relationship
- RebateConfig: global rebate settings (rate, cost ratio) set by super admin
- RebateRecord: immutable ledger of daily rebate settlements
"""

import enum
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import TypeBase
from .types import LongText, StringUUID


class BillingRecordType(enum.StrEnum):
    DEDUCTION = "deduction"
    TOPUP = "topup"
    REBATE = "rebate"  # rebate income credited to inviter's balance
    ALLOCATION = "allocation"  # tenant -> member fund allocation


class CreatorWorkShareStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED_TIKTOK = "published_tiktok"
    PUBLISHED_XHS = "published_xhs"


class UserBalance(TypeBase):
    """Per-account balance pool.

    One row per account. Balance can go negative — user must repay debt
    before running further workflows.
    """

    __tablename__ = "user_balances"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="user_balance_pkey"),
        sa.Index("user_balance_account_id_idx", "account_id", unique=True),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    balance: Mapped[Decimal] = mapped_column(sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(10), server_default="CNY", default="CNY")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )

    def is_sufficient(self) -> bool:
        """Return True if balance > 0."""
        return self.balance > Decimal(0)


class BillingRecord(TypeBase):
    """Immutable ledger entry for each deduction or top-up."""

    __tablename__ = "billing_records"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="billing_record_pkey"),
        sa.Index("billing_record_account_id_idx", "account_id"),
        sa.Index("billing_record_tenant_id_idx", "tenant_id"),
        sa.Index("billing_record_account_created_idx", "account_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(precision=20, scale=6), nullable=False)
    record_type: Mapped[str] = mapped_column(String(20), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    workflow_run_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    currency: Mapped[str] = mapped_column(String(10), server_default="CNY", default="CNY")
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
    scope: Mapped[str] = mapped_column(String(20), server_default="user", default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )

    @property
    def record_type_enum(self) -> BillingRecordType:
        return BillingRecordType(self.record_type)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "tenant_id": self.tenant_id,
            "workflow_run_id": self.workflow_run_id,
            "amount": str(self.amount),
            "currency": self.currency,
            "record_type": self.record_type,
            "description": self.description,
            "scope": self.scope,
            "created_at": self.created_at.isoformat(),
        }


class MarketplaceApp(TypeBase):
    """Workflow apps published to the platform marketplace by super admins."""

    __tablename__ = "marketplace_apps"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="marketplace_app_pkey"),
        sa.Index("marketplace_app_app_id_idx", "app_id", unique=True),
        sa.Index("marketplace_app_published_at_idx", "published_at"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    app_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    published_by: Mapped[str] = mapped_column(StringUUID, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    display_order: Mapped[int] = mapped_column(sa.Integer, server_default="0", default=0)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.text("true"), default=True)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.text("false"), default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "app_id": self.app_id,
            "published_by": self.published_by,
            "published_at": self.published_at.isoformat(),
            "display_order": self.display_order,
            "is_active": self.is_active,
            "is_default": self.is_default,
        }


class UserGlobalApiKey(TypeBase):
    """User-level global API key that applies to all apps the user has access to.

    Overrides per-app API key configuration when present.
    """

    __tablename__ = "user_global_api_keys"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="user_global_api_key_pkey"),
        sa.Index("user_global_api_key_account_id_idx", "account_id", unique=True),
        sa.Index("user_global_api_key_token_idx", "token", unique=True),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    token: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )

    def to_dict(self, masked: bool = True) -> dict:
        token_display = f"{self.token[:8]}...{self.token[-4:]}" if masked and len(self.token) > 12 else self.token
        return {
            "id": self.id,
            "account_id": self.account_id,
            "token": token_display,
            "description": self.description,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat(),
        }


class CreatorWork(TypeBase):
    """Content generated by a creator through a workflow run.

    Tracks videos or other outputs that can be shared to social platforms.
    """

    __tablename__ = "creator_works"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="creator_work_pkey"),
        sa.Index("creator_work_account_id_idx", "account_id"),
        sa.Index("creator_work_tenant_id_idx", "tenant_id"),
        sa.Index("creator_work_created_at_idx", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    workflow_run_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    app_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    file_type: Mapped[str] = mapped_column(String(50), server_default="video", default="video")
    share_status: Mapped[str] = mapped_column(String(50), server_default="draft", default="draft")
    output_data: Mapped[str | None] = mapped_column(LongText, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "tenant_id": self.tenant_id,
            "workflow_run_id": self.workflow_run_id,
            "app_id": self.app_id,
            "title": self.title,
            "file_key": self.file_key,
            "file_type": self.file_type,
            "share_status": self.share_status,
            "output_data": self.output_data,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Invitation & Rebate models
# ---------------------------------------------------------------------------


class AccountInvitation(TypeBase):
    """Tracks invitation codes and the parent→child referral relationship.

    Each workspace owner can generate an invite code.  When a new user registers
    with that code, a row is inserted linking inviter (parent) → invitee (child).
    """

    __tablename__ = "account_invitations"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="account_invitation_pkey"),
        sa.Index("account_invitation_code_idx", "invite_code", unique=True),
        sa.Index("account_invitation_inviter_idx", "inviter_account_id"),
        sa.Index("account_invitation_invitee_idx", "invitee_account_id"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    invite_code: Mapped[str] = mapped_column(String(64), nullable=False)
    inviter_account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    invitee_account_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    status: Mapped[str] = mapped_column(
        String(20), server_default="pending", default="pending"
    )  # pending | used | revoked
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "invite_code": self.invite_code,
            "inviter_account_id": self.inviter_account_id,
            "invitee_account_id": self.invitee_account_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "used_at": self.used_at.isoformat() if self.used_at else None,
        }


class RebateConfig(TypeBase):
    """Global rebate configuration set by super admin.

    Only one active row should exist at any time.

    Rebate is calculated based on each invitee's **consumption** (deductions)
    from the previous day — NOT on top-ups.  Different models have different
    token prices, but deduction records already reflect the actual cost in
    CNY, so the amount field is model-agnostic.

    Fields:
    - rebate_rate: percentage (0–100) of the *profit* (or gross consumption if
      cost_rate is 0) that goes to the inviter.
    - cost_rate: percentage (0–100) representing our platform cost.  When > 0,
      rebate = consumption * (1 - cost_rate/100) * rebate_rate/100.
      When 0, rebate = consumption * rebate_rate/100.
    - settlement_hour: hour of day (0–23, server timezone) when the daily
      settlement task runs.
    """

    __tablename__ = "rebate_configs"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="rebate_config_pkey"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    rebate_rate: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=10, scale=4), server_default="10", default=Decimal(10)
    )  # default 10%
    cost_rate: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=10, scale=4), server_default="0", default=Decimal(0)
    )  # default 0 = no cost deduction
    settlement_hour: Mapped[int] = mapped_column(
        sa.Integer, server_default="2", default=2
    )  # default 02:00
    is_enabled: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.text("true"), default=True
    )
    updated_by: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False,
        onupdate=func.current_timestamp()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rebate_rate": str(self.rebate_rate),
            "cost_rate": str(self.cost_rate),
            "settlement_hour": self.settlement_hour,
            "is_enabled": self.is_enabled,
            "updated_by": self.updated_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class RebateRecord(TypeBase):
    """Immutable ledger for each rebate settlement.

    One record per inviter *per invitee* per settlement day, summarising the
    rebate earned from that invitee's consumption (deductions) on that day.
    """

    __tablename__ = "rebate_records"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="rebate_record_pkey"),
        sa.Index("rebate_record_inviter_idx", "inviter_account_id"),
        sa.Index("rebate_record_invitee_idx", "invitee_account_id"),
        sa.Index("rebate_record_date_idx", "settlement_date"),
        sa.Index("rebate_record_inviter_date_idx", "inviter_account_id", "settlement_date"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    inviter_account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    invitee_account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    settlement_date: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # YYYY-MM-DD
    consumption_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), nullable=False
    )  # total consumption by invitee on that day
    rebate_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), nullable=False
    )  # actual rebate credited to inviter
    rebate_rate: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=10, scale=4), nullable=False
    )  # snapshot of rate at settlement time
    # --- fields with defaults must come after non-default fields ---
    cost_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0)
    )  # cost deducted
    cost_rate: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=10, scale=4), server_default="0", default=Decimal(0)
    )  # snapshot of cost rate
    currency: Mapped[str] = mapped_column(String(10), server_default="CNY", default="CNY")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "inviter_account_id": self.inviter_account_id,
            "invitee_account_id": self.invitee_account_id,
            "settlement_date": self.settlement_date,
            "consumption_amount": str(self.consumption_amount),
            "cost_amount": str(self.cost_amount),
            "rebate_amount": str(self.rebate_amount),
            "rebate_rate": str(self.rebate_rate),
            "cost_rate": str(self.cost_rate),
            "currency": self.currency,
            "created_at": self.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Payment / Wallet models
# ---------------------------------------------------------------------------


class PaymentProviderName(enum.StrEnum):
    ALIPAY = "alipay"
    WECHAT = "wechat"


class PaymentOrderStatus(enum.StrEnum):
    PENDING = "pending"
    PAID = "paid"
    CLOSED = "closed"
    REFUNDED = "refunded"
    FAILED = "failed"


class TenantBalance(TypeBase):
    """Workspace-level wallet."""

    __tablename__ = "tenant_balances"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="tenant_balance_pkey"),
        sa.Index("tenant_balance_tenant_id_idx", "tenant_id", unique=True),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    balance: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0)
    )
    locked: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0)
    )
    total_topup: Mapped[Decimal] = mapped_column(
        sa.Numeric(precision=20, scale=6), server_default="0", default=Decimal(0)
    )
    currency: Mapped[str] = mapped_column(String(10), server_default="CNY", default="CNY")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )

    @property
    def total(self) -> Decimal:
        return self.balance + self.locked


class PaymentOrder(TypeBase):
    """Top-up payment order, provider-agnostic."""

    __tablename__ = "payment_orders"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="payment_order_pkey"),
        sa.Index("payment_order_out_trade_no_idx", "out_trade_no", unique=True),
        sa.Index("payment_order_tenant_status_idx", "tenant_id", "status"),
        sa.Index("payment_order_provider_trade_idx", "provider", "provider_trade_no"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    out_trade_no: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(precision=20, scale=6), nullable=False)
    amount_fen: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    # --- fields with defaults must come after non-default fields ---
    provider_trade_no: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentOrderStatus.PENDING.value)
    qr_code: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    prepay_raw: Mapped[str | None] = mapped_column(LongText, nullable=True, default=None)
    notify_raw: Mapped[str | None] = mapped_column(LongText, nullable=True, default=None)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False, onupdate=func.current_timestamp()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "out_trade_no": self.out_trade_no,
            "provider_trade_no": self.provider_trade_no,
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "amount": str(self.amount),
            "amount_fen": self.amount_fen,
            "subject": self.subject,
            "status": self.status,
            "qr_code": self.qr_code,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat(),
        }


class AllocationRecord(TypeBase):
    """Ledger for tenant -> member fund movements."""

    __tablename__ = "allocation_records"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="allocation_record_pkey"),
        sa.Index("alloc_tenant_created_idx", "tenant_id", "created_at"),
        sa.Index("alloc_member_idx", "account_id"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID, insert_default=lambda: str(uuid4()), default_factory=lambda: str(uuid4()), init=False
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    operator_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(precision=20, scale=6), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "account_id": self.account_id,
            "operator_id": self.operator_id,
            "amount": str(self.amount),
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }
