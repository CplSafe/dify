"""SQLAlchemy implementation of SocialPublishTaskRepository.

Same defence-in-depth posture as the account repository: tenant_id is a
WHERE-clause invariant, terminal-state updates are idempotent, and the
single-flight check uses ACTIVE_TASK_STATUSES so terminal rows don't block
new publishes.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session, sessionmaker

from models.social_publish import (
    ACTIVE_TASK_STATUSES,
    SocialPublishTask,
    SocialPublishTaskStatus,
)
from repositories.social_publish_task_repository import SocialPublishTaskRepository


class DifyAPISQLAlchemySocialPublishTaskRepository(SocialPublishTaskRepository):
    def __init__(self, session_maker: sessionmaker[Session]) -> None:
        self._session_maker = session_maker

    def create(
        self,
        *,
        tenant_id: str,
        account_id: str,
        platform: str,
        payload: dict[str, Any],
        created_by: str,
        work_id: str | None,
    ) -> SocialPublishTask:
        with self._session_maker() as session:
            row = SocialPublishTask(
                tenant_id=tenant_id,
                account_id=account_id,
                platform=platform,
                payload=payload,
                created_by=created_by,
                work_id=work_id,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def get_by_id_and_tenant(
        self,
        task_id: str,
        tenant_id: str,
    ) -> SocialPublishTask | None:
        with self._session_maker() as session:
            stmt = select(SocialPublishTask).where(
                SocialPublishTask.id == task_id,
                SocialPublishTask.tenant_id == tenant_id,
            )
            return session.execute(stmt).scalar_one_or_none()

    def list_by_tenant(
        self,
        tenant_id: str,
        *,
        account_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> Sequence[SocialPublishTask]:
        with self._session_maker() as session:
            stmt = select(SocialPublishTask).where(
                SocialPublishTask.tenant_id == tenant_id,
            )
            if account_id is not None:
                stmt = stmt.where(SocialPublishTask.account_id == account_id)
            if status is not None:
                stmt = stmt.where(SocialPublishTask.status == status)
            stmt = stmt.order_by(SocialPublishTask.created_at.desc()).limit(limit)
            return session.execute(stmt).scalars().all()

    def has_active_for_account(self, *, tenant_id: str, account_id: str) -> bool:
        with self._session_maker() as session:
            stmt = select(
                exists().where(
                    SocialPublishTask.tenant_id == tenant_id,
                    SocialPublishTask.account_id == account_id,
                    SocialPublishTask.status.in_(ACTIVE_TASK_STATUSES),
                )
            )
            return bool(session.execute(stmt).scalar())

    def attach_sau_task_id(
        self,
        *,
        task_id: str,
        tenant_id: str,
        sau_task_id: str,
    ) -> SocialPublishTask | None:
        with self._session_maker() as session:
            stmt = (
                update(SocialPublishTask)
                .where(
                    SocialPublishTask.id == task_id,
                    SocialPublishTask.tenant_id == tenant_id,
                )
                .values(
                    sau_task_id=sau_task_id,
                    status=SocialPublishTaskStatus.QUEUED.value,
                )
                .returning(SocialPublishTask)
            )
            row = session.execute(stmt).scalar_one_or_none()
            session.commit()
            return row

    def update_terminal(
        self,
        *,
        task_id: str,
        tenant_id: str,
        status: str,
        result_url: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> SocialPublishTask | None:
        # Idempotent guard: if the row is already in a terminal state, skip
        # the update so concurrent pollers don't overwrite each other.
        terminal = (
            SocialPublishTaskStatus.SUCCESS.value,
            SocialPublishTaskStatus.FAILED.value,
        )
        values: dict[str, Any] = {"status": status}
        if result_url is not None:
            values["result_url"] = result_url
        if error_code is not None:
            values["error_code"] = error_code
        if error_message is not None:
            # Cap to avoid pathological logs blowing up the column.
            values["error_message"] = error_message[:4000]
        with self._session_maker() as session:
            stmt = (
                update(SocialPublishTask)
                .where(
                    SocialPublishTask.id == task_id,
                    SocialPublishTask.tenant_id == tenant_id,
                    SocialPublishTask.status.notin_(terminal),
                )
                .values(**values)
                .returning(SocialPublishTask)
            )
            row = session.execute(stmt).scalar_one_or_none()
            session.commit()
            if row is None:
                # Already terminal — return current row for observability.
                return self.get_by_id_and_tenant(task_id, tenant_id)
            return row

    def update_status_to_running(
        self,
        *,
        task_id: str,
        tenant_id: str,
    ) -> SocialPublishTask | None:
        # Only flip queued -> running so we never regress from a terminal
        # state or overshoot success.
        with self._session_maker() as session:
            stmt = (
                update(SocialPublishTask)
                .where(
                    SocialPublishTask.id == task_id,
                    SocialPublishTask.tenant_id == tenant_id,
                    SocialPublishTask.status == SocialPublishTaskStatus.QUEUED.value,
                )
                .values(status=SocialPublishTaskStatus.RUNNING.value)
                .returning(SocialPublishTask)
            )
            row = session.execute(stmt).scalar_one_or_none()
            session.commit()
            return row
