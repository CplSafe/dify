"""Creator task model.

Tracks chatflow tasks initiated by creators. Tasks persist across page
navigations so users can close the page and resume later.
"""

import enum
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import TypeBase
from .types import StringUUID


class CreatorTaskStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_in_progress(self) -> bool:
        return self in (CreatorTaskStatus.RUNNING, CreatorTaskStatus.WAITING_INPUT)


class CreatorTask(TypeBase):
    """A chatflow task created by a user in the creator workspace.

    Persists across page closures. The server-side workflow continues running
    regardless of whether the frontend is connected.
    """

    __tablename__ = "creator_tasks"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="creator_task_pkey"),
        sa.Index("idx_creator_tasks_user_status", "account_id", "status", "created_at"),
        sa.Index("idx_creator_tasks_conversation", "conversation_id"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID,
        insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()),
        init=False,
    )
    account_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    app_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    installed_app_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    workflow_run_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    status: Mapped[str] = mapped_column(
        String(20), server_default="running", default=CreatorTaskStatus.RUNNING.value
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
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
    def status_enum(self) -> CreatorTaskStatus:
        return CreatorTaskStatus(self.status)

    @property
    def is_in_progress(self) -> bool:
        return self.status_enum.is_in_progress

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "tenant_id": self.tenant_id,
            "app_id": self.app_id,
            "installed_app_id": self.installed_app_id,
            "conversation_id": self.conversation_id,
            "workflow_run_id": self.workflow_run_id,
            "status": self.status,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
