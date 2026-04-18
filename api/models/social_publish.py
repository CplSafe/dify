"""Social publish models.

Includes:
- SocialPublishAccount: per-tenant binding to a sau-managed platform account
  (douyin / xhs / ks). The cookie file lives in the sau service; this row
  carries only the metadata Dify needs for listing, status display and
  authorization checks.
- SocialPublishTask: an asynchronous publish-to-sau attempt. One row per
  request from the publish drawer. The Celery task id from sau lives in
  ``sau_task_id`` so we can poll for state updates.
"""

import enum
from datetime import datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import TypeBase
from .types import AdjustedJSON, StringUUID


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


class SocialPublishTaskStatus(enum.StrEnum):
    """Lifecycle of a SocialPublishTask row.

    - ``PENDING``: row created locally, sau dispatch not yet attempted.
    - ``QUEUED``: sau acknowledged the multipart upload and returned a
      ``sau_task_id``; the Celery task is in the broker queue.
    - ``RUNNING``: Celery worker has picked up the task (best-effort signal,
      polled from sau ``GET /tasks/{id}``).
    - ``SUCCESS``: terminal — ``result_url`` is populated when available.
    - ``FAILED``: terminal — ``error_code`` + ``error_message`` are filled.

    The "active" set (anything not terminal) is what the service queries to
    enforce per-account single-flight publishing.
    """

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


ACTIVE_TASK_STATUSES: tuple[str, ...] = (
    SocialPublishTaskStatus.PENDING.value,
    SocialPublishTaskStatus.QUEUED.value,
    SocialPublishTaskStatus.RUNNING.value,
)


class SocialPublishTask(TypeBase):
    """An asynchronous publish-to-platform attempt.

    Tenant isolation invariant identical to SocialPublishAccount: the
    tenant_id column is sourced exclusively from the resolved account row,
    NEVER from the request body. Every read/write through the repository
    constrains by tenant_id in the WHERE clause.
    """

    __tablename__ = "social_publish_tasks"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="social_publish_task_pkey"),
        sa.Index("social_publish_task_tenant_created_idx", "tenant_id", "created_at"),
        sa.Index("social_publish_task_account_idx", "account_id"),
        sa.Index("social_publish_task_status_idx", "status"),
        # P3 quota check is `WHERE tenant_id = ? AND status IN (...)` —
        # the (tenant_id, status) composite covers it directly so the
        # planner doesn't have to scan the whole tenant slice.
        sa.Index("social_publish_task_tenant_status_idx", "tenant_id", "status"),
        # Partial index — sau_task_id is nullable until /postVideo dispatch
        # succeeds; we never query by NULL.
        sa.Index(
            "social_publish_task_sau_task_idx",
            "sau_task_id",
            postgresql_where=sa.text("sau_task_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(
        StringUUID,
        insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()),
        init=False,
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        AdjustedJSON(astext_type=sa.Text()),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(StringUUID, nullable=False)
    work_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    status: Mapped[str] = mapped_column(
        String(16),
        server_default=SocialPublishTaskStatus.PENDING.value,
        default=SocialPublishTaskStatus.PENDING.value,
    )
    sau_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    result_url: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(sa.Text(), nullable=True, default=None)
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
    def status_enum(self) -> SocialPublishTaskStatus:
        return SocialPublishTaskStatus(self.status)

    def is_terminal(self) -> bool:
        return self.status in (
            SocialPublishTaskStatus.SUCCESS.value,
            SocialPublishTaskStatus.FAILED.value,
        )

    def to_dict(self) -> dict:
        # tenant_id is intentionally NOT exposed; the caller already knows
        # which tenant they're scoped to.
        return {
            "id": self.id,
            "account_id": self.account_id,
            "work_id": self.work_id,
            "platform": self.platform,
            "status": self.status,
            "result_url": self.result_url,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<SocialPublishTask id={self.id} tenant={self.tenant_id} "
            f"status={self.status}>"
        )
