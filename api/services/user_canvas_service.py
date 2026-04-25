"""Service for canvas-runtime saved canvases.

A `UserCanvas` row is a user's named pointer to a successful
`workflow_run`. The actual node + IO snapshot is re-derived from
`workflow_runs` / `workflow_node_executions` on open — this service
only owns naming, ownership, and lifecycle.

Tenant + owner isolation is enforced inside the service so callers
can't pass a forged `owner_id` from the request body.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select

from extensions.ext_database import db
from models.model import App
from models.workflow import UserCanvas, WorkflowRun

logger = logging.getLogger(__name__)


# Hard limit so a runaway script can't fill the table for a single user.
# Old canvases are returned in the list but new ones above this cap are
# rejected with CanvasQuotaExceededError so the user knows to delete first.
_MAX_CANVASES_PER_OWNER = 200


class CanvasValidationError(ValueError):
    """Raised when a canvas request fails preconditions (bad title, run, etc.)."""


class CanvasNotFoundError(LookupError):
    """Raised when the canvas row is missing OR not owned by the caller.

    We deliberately collapse "not found" and "not yours" into the same
    error so an attacker can't enumerate canvas IDs across owners.
    """


class CanvasQuotaExceededError(RuntimeError):
    """Raised when the owner already has _MAX_CANVASES_PER_OWNER rows."""


class UserCanvasService:
    @classmethod
    def list_for_owner(
        cls,
        *,
        tenant_id: str,
        owner_id: str,
        app_id: str | None = None,
    ) -> Sequence[UserCanvas]:
        """Newest first. Optionally filtered by app_id."""
        stmt = (
            select(UserCanvas)
            .where(UserCanvas.tenant_id == tenant_id)
            .where(UserCanvas.owner_id == owner_id)
            .order_by(UserCanvas.created_at.desc())
        )
        if app_id:
            stmt = stmt.where(UserCanvas.app_id == app_id)
        return db.session.execute(stmt).scalars().all()

    @classmethod
    def get_for_owner(
        cls,
        *,
        tenant_id: str,
        owner_id: str,
        canvas_id: str,
    ) -> UserCanvas:
        """Fetch a canvas, enforcing owner + tenant scope."""
        row = db.session.execute(
            select(UserCanvas)
            .where(UserCanvas.id == canvas_id)
            .where(UserCanvas.tenant_id == tenant_id)
            .where(UserCanvas.owner_id == owner_id)
        ).scalar_one_or_none()
        if row is None:
            raise CanvasNotFoundError(f"canvas {canvas_id!r} not found")
        return row

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        owner_id: str,
        app: App,
        title: str,
        source_run_id: str,
    ) -> UserCanvas:
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            raise CanvasValidationError("title is required")
        if len(cleaned_title) > 200:
            raise CanvasValidationError("title must be at most 200 characters")
        if str(app.tenant_id) != tenant_id:
            raise CanvasValidationError("app does not belong to the tenant")

        # Verify the source_run_id actually points at a workflow_run for
        # this app — protects against users saving an arbitrary run id.
        run = db.session.execute(
            select(WorkflowRun)
            .where(WorkflowRun.id == source_run_id)
            .where(WorkflowRun.tenant_id == tenant_id)
            .where(WorkflowRun.app_id == str(app.id))
        ).scalar_one_or_none()
        if run is None:
            raise CanvasValidationError(
                f"workflow_run {source_run_id!r} not found for this app"
            )

        # Quota check.
        existing_count = (
            db.session.execute(
                select(UserCanvas.id)
                .where(UserCanvas.tenant_id == tenant_id)
                .where(UserCanvas.owner_id == owner_id)
            )
            .scalars()
            .all()
        )
        if len(existing_count) >= _MAX_CANVASES_PER_OWNER:
            raise CanvasQuotaExceededError(
                f"canvas quota of {_MAX_CANVASES_PER_OWNER} reached; "
                "delete an old canvas first"
            )

        row = UserCanvas(
            tenant_id=tenant_id,
            app_id=str(app.id),
            owner_id=owner_id,
            title=cleaned_title,
            source_run_id=source_run_id,
        )
        db.session.add(row)
        db.session.commit()
        db.session.refresh(row)
        return row

    @classmethod
    def rename(
        cls,
        *,
        tenant_id: str,
        owner_id: str,
        canvas_id: str,
        title: str,
    ) -> UserCanvas:
        cleaned = (title or "").strip()
        if not cleaned:
            raise CanvasValidationError("title is required")
        if len(cleaned) > 200:
            raise CanvasValidationError("title must be at most 200 characters")
        row = cls.get_for_owner(
            tenant_id=tenant_id, owner_id=owner_id, canvas_id=canvas_id
        )
        row.title = cleaned
        db.session.commit()
        db.session.refresh(row)
        return row

    @classmethod
    def delete(
        cls,
        *,
        tenant_id: str,
        owner_id: str,
        canvas_id: str,
    ) -> None:
        row = cls.get_for_owner(
            tenant_id=tenant_id, owner_id=owner_id, canvas_id=canvas_id
        )
        db.session.delete(row)
        db.session.commit()
