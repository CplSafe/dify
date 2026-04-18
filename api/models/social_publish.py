"""Social publish models.

Includes:
- SocialPublishAccount: per-tenant binding to a sau-managed platform account
  (douyin / xhs / ks). The cookie file lives in the sau service; this row
  carries only the metadata Dify needs for listing, status display and
  authorization checks.
"""

import enum
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import TypeBase
from .types import StringUUID


class SocialPublishPlatform(enum.StrEnum):
    """Supported social publishing platforms.

    Only ``DOUYIN`` is wired up in P1; xhs/ks reserve their slot so the
    platform column accepts them when P4 enables the other uploaders.
    """

    DOUYIN = "douyin"
    XHS = "xhs"
    KS = "ks"


class SocialPublishAccountStatus(enum.StrEnum):
    """Lifecycle of a SocialPublishAccount row.

    - ``PENDING_AUTH``: row was just created during the auth flow but the
      cookie has not yet been verified by sau.
    - ``ACTIVE``: cookie is valid and the account can publish.
    - ``EXPIRED``: cookie expired or sau reported the account no longer
      authenticates. UI surfaces a "re-authorize" button.
    """

    PENDING_AUTH = "pending_auth"
    ACTIVE = "active"
    EXPIRED = "expired"


class SocialPublishAccount(TypeBase):
    """Tenant-scoped binding to a platform account managed by sau.

    Tenant isolation invariant: every read/write through the repository must
    constrain by ``tenant_id``. The unique index on ``sau_account_id`` is a
    *global* invariant (sau never reuses an account id across tenants), but
    the repository must still enforce tenant scoping in WHERE clauses to
    prevent cross-tenant disclosure even if sau ever regressed.
    """

    __tablename__ = "social_publish_accounts"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="social_publish_account_pkey"),
        sa.Index("social_publish_account_tenant_platform_idx", "tenant_id", "platform"),
        sa.Index("social_publish_account_sau_account_id_uk", "sau_account_id", unique=True),
        sa.Index("social_publish_account_status_idx", "status"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID,
        insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()),
        init=False,
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    sau_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(StringUUID, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    avatar_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
    status: Mapped[str] = mapped_column(
        String(16),
        server_default=SocialPublishAccountStatus.PENDING_AUTH.value,
        default=SocialPublishAccountStatus.PENDING_AUTH.value,
    )
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False, init=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        nullable=False,
        init=False,
        onupdate=func.current_timestamp(),
    )

    @property
    def platform_enum(self) -> SocialPublishPlatform:
        return SocialPublishPlatform(self.platform)

    @property
    def status_enum(self) -> SocialPublishAccountStatus:
        return SocialPublishAccountStatus(self.status)

    def to_dict(self) -> dict:
        # tenant_id is intentionally NOT exposed: callers already know which
        # tenant they are scoped to, and leaking it could let a UI bug surface
        # cross-tenant ids in a logs/screenshot leak.
        return {
            "id": self.id,
            "platform": self.platform,
            "display_name": self.display_name,
            "avatar_url": self.avatar_url,
            "status": self.status,
            "last_check_at": self.last_check_at.isoformat() if self.last_check_at else None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<SocialPublishAccount id={self.id} tenant={self.tenant_id} "
            f"platform={self.platform} status={self.status}>"
        )
