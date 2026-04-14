"""Creator task service.

Handles task creation, status updates (with optimistic locking), and queries.
Enforces the per-user concurrent task limit.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from werkzeug.exceptions import Conflict, NotFound, TooManyRequests

from extensions.ext_database import db
from models.creator_task import CreatorTask, CreatorTaskStatus

MAX_IN_PROGRESS_TASKS = 10
MAX_COMPLETED_TASKS = 50
LIST_PAGE_SIZE = 20
TASK_TIMEOUT_HOURS = 24


class CreatorTaskService:

    @staticmethod
    def create_task(
        account_id: str,
        tenant_id: str,
        app_id: str,
        installed_app_id: str,
        conversation_id: str | None,
        workflow_run_id: str | None,
        title: str | None,
    ) -> CreatorTask:
        """Create a new task. Raises TooManyRequests if concurrent limit exceeded."""
        in_progress_count = db.session.scalar(
            select(func.count()).select_from(
                select(CreatorTask)
                .where(
                    CreatorTask.account_id == account_id,
                    CreatorTask.status.in_([
                        CreatorTaskStatus.RUNNING.value,
                        CreatorTaskStatus.WAITING_INPUT.value,
                        CreatorTaskStatus.PENDING.value,
                    ]),
                )
                .subquery()
            )
        ) or 0

        if in_progress_count >= MAX_IN_PROGRESS_TASKS:
            raise TooManyRequests(
                f"Maximum of {MAX_IN_PROGRESS_TASKS} concurrent tasks allowed. "
                "Please wait for a task to complete before starting a new one."
            )

        task = CreatorTask(
            account_id=account_id,
            tenant_id=tenant_id,
            app_id=app_id,
            installed_app_id=installed_app_id,
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
            status=CreatorTaskStatus.RUNNING.value,
            title=title,
        )
        db.session.add(task)
        db.session.commit()
        return task

    @staticmethod
    def update_task(
        task_id: str,
        account_id: str,
        new_status: str | None,
        new_title: str | None,
        last_updated_at: datetime | None,
    ) -> CreatorTask:
        """Update task status and/or title with optimistic locking on status changes.

        Raises Conflict if the task was modified between read and write (status change only).
        Raises NotFound if the task does not exist or belongs to another user.
        """
        task = db.session.scalar(
            select(CreatorTask).where(
                CreatorTask.id == task_id,
                CreatorTask.account_id == account_id,
            )
        )
        if not task:
            raise NotFound("Task not found.")

        if new_status is not None and last_updated_at is not None:
            stored_ts = int(task.updated_at.replace(tzinfo=UTC).timestamp())
            provided_ts = int(last_updated_at.timestamp())
            if stored_ts != provided_ts:
                raise Conflict("Task was modified by another request. Re-fetch and retry.")

        if new_status is not None:
            task.status = new_status
        if new_title is not None:
            task.title = new_title or None

        db.session.add(task)
        db.session.commit()

        if new_status == CreatorTaskStatus.COMPLETED.value:
            CreatorTaskService._prune_completed_tasks(account_id)

        return task

    @staticmethod
    def delete_task(task_id: str, account_id: str) -> None:
        """Delete a task owned by the given account.

        Raises NotFound if the task does not exist or belongs to another user.
        """
        task = db.session.scalar(
            select(CreatorTask).where(
                CreatorTask.id == task_id,
                CreatorTask.account_id == account_id,
            )
        )
        if not task:
            raise NotFound("Task not found.")
        db.session.delete(task)
        db.session.commit()

    @staticmethod
    def get_task(task_id: str, account_id: str) -> CreatorTask:
        task = db.session.scalar(
            select(CreatorTask).where(
                CreatorTask.id == task_id,
                CreatorTask.account_id == account_id,
            )
        )
        if not task:
            raise NotFound("Task not found.")
        return task

    @staticmethod
    def list_tasks(account_id: str) -> dict:
        """Return the most recent tasks for the user, newest first."""
        tasks = list(
            db.session.scalars(
                select(CreatorTask)
                .where(CreatorTask.account_id == account_id)
                .order_by(CreatorTask.created_at.desc())
                .limit(LIST_PAGE_SIZE)
            ).all()
        )

        total = db.session.scalar(
            select(func.count()).select_from(
                select(CreatorTask).where(CreatorTask.account_id == account_id).subquery()
            )
        ) or 0

        in_progress_count = sum(1 for t in tasks if t.is_in_progress)

        return {
            "tasks": [t.to_dict() for t in tasks],
            "total": total,
            "in_progress_count": in_progress_count,
        }

    @staticmethod
    def _prune_completed_tasks(account_id: str) -> None:
        """Keep only the most recent MAX_COMPLETED_TASKS completed tasks per user."""
        completed = list(
            db.session.scalars(
                select(CreatorTask)
                .where(
                    CreatorTask.account_id == account_id,
                    CreatorTask.status == CreatorTaskStatus.COMPLETED.value,
                )
                .order_by(CreatorTask.created_at.desc())
            ).all()
        )

        if len(completed) > MAX_COMPLETED_TASKS:
            for old_task in completed[MAX_COMPLETED_TASKS:]:
                db.session.delete(old_task)
            db.session.commit()

    @staticmethod
    def timeout_stale_tasks() -> int:
        """Mark tasks older than TASK_TIMEOUT_HOURS as failed. Returns count updated."""
        cutoff = datetime.now(UTC) - timedelta(hours=TASK_TIMEOUT_HOURS)
        stale_tasks = list(
            db.session.scalars(
                select(CreatorTask).where(
                    CreatorTask.status.in_([
                        CreatorTaskStatus.RUNNING.value,
                        CreatorTaskStatus.WAITING_INPUT.value,
                        CreatorTaskStatus.PENDING.value,
                    ]),
                    CreatorTask.created_at < cutoff,
                )
            ).all()
        )

        for task in stale_tasks:
            task.status = CreatorTaskStatus.FAILED.value
            db.session.add(task)

        if stale_tasks:
            db.session.commit()

        return len(stale_tasks)
