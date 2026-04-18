"""Publish-task orchestration for the publish-center.

Distinct from ``social_publish_service.py`` (account management) because:
- the dependency graph is bigger (storage + sau client + 2 repos + work
  validation) and bundling everything would inflate the test surface;
- the publish flow has its own single-flight + size-limit invariants that
  are easier to reason about in isolation.

Tenant isolation rules (mirroring the account service):
- ``account_id`` and ``work_id`` from the request are resolved through
  tenant-scoped lookups — they are never trusted as-is.
- ``social_publish_task.tenant_id`` is sourced from the resolved account
  row, never from the request body.
- Every status read filters by tenant_id in SQL; cross-tenant probes
  return ``TaskNotFoundError``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from configs import dify_config
from extensions.ext_redis import redis_client
from extensions.ext_storage import storage
from models.creator import CreatorWork
from models.engine import db
from models.social_publish import (
    SocialPublishAccount,
    SocialPublishAccountStatus,
    SocialPublishTask,
    SocialPublishTaskStatus,
)
from repositories.social_publish_account_repository import (
    SocialPublishAccountRepository,
)
from repositories.social_publish_task_repository import (
    SocialPublishTaskRepository,
)
from services.errors.social_publish import (
    AccountExpiredError,
    AccountNotFoundError,
    PlatformUnsupportedError,
    SauApiError,
    SauUnreachableError,
    TaskAlreadyInFlightError,
    TaskInvalidPayloadError,
    TaskNotFoundError,
    VideoNotFoundError,
    VideoTooLargeError,
    WorkNotFoundError,
)
from services.sau_client import SauClient

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS_P2 = ("douyin",)
TITLE_MAX_LEN = 200
DESC_MAX_LEN = 2000
TAGS_MAX_COUNT = 10

# Single-flight Redis lock TTL — covers the worst-case time between the
# initial check and the persisted attach_sau_task_id. The downstream
# Celery task itself takes much longer; the lock only guards the
# enqueue race, so this short TTL is fine.
SINGLE_FLIGHT_LOCK_TTL_SECONDS = 60


def _single_flight_lock_key(tenant_id: str, account_id: str) -> str:
    return f"sau:publish:single_flight:{tenant_id}:{account_id}"


# ---------- DTOs ----------


@dataclass(frozen=True)
class CreateTaskRequest:
    account_id: str
    work_id: str | None
    title: str
    tags: list[str] | None
    desc: str | None


@dataclass(frozen=True)
class TaskStatusResponse:
    task: dict[str, Any]
    result: dict[str, Any]


# ---------- Service ----------


class SocialPublishTaskService:
    def __init__(
        self,
        *,
        task_repository: SocialPublishTaskRepository,
        account_repository: SocialPublishAccountRepository,
        sau_client: SauClient,
    ) -> None:
        self._tasks = task_repository
        self._accounts = account_repository
        self._sau = sau_client

    # ----- create -----

    def create_task(
        self,
        *,
        tenant_id: str,
        created_by: str,
        request: CreateTaskRequest,
    ) -> SocialPublishTask:
        account = self._resolve_account(tenant_id=tenant_id, account_id=request.account_id)
        if account.status != SocialPublishAccountStatus.ACTIVE.value:
            # Surface a typed error so the FE can drop straight into the
            # re-auth flow instead of a generic failure message.
            raise AccountExpiredError(
                f"account {account.id} is in status {account.status!r}, re-authorize first"
            )

        if account.platform not in SUPPORTED_PLATFORMS_P2:
            raise PlatformUnsupportedError(
                f"platform {account.platform!r} is not supported in P2"
            )

        payload = self._validate_payload(request)
        work = self._resolve_work(tenant_id=tenant_id, work_id=request.work_id)
        video_bytes, video_filename = self._load_video(work)

        # Atomic single-flight: take a Redis SET NX lock keyed by
        # (tenant, account) BEFORE the DB check, so two concurrent requests
        # from the same workspace can't both pass the has_active_for_account
        # gate. The lock is released in the ``finally`` after dispatch
        # succeeds (the row is now persisted with status=queued, and
        # has_active_for_account picks it up on the next attempt).
        lock_key = _single_flight_lock_key(tenant_id, account.id)
        if not redis_client.set(
            lock_key, "1", nx=True, ex=SINGLE_FLIGHT_LOCK_TTL_SECONDS
        ):
            raise TaskAlreadyInFlightError(
                f"account {account.id} already has an in-flight publish dispatch"
            )

        try:
            if self._tasks.has_active_for_account(
                tenant_id=tenant_id, account_id=account.id
            ):
                raise TaskAlreadyInFlightError(
                    f"account {account.id} already has an in-flight publish task"
                )

            task = self._tasks.create(
                tenant_id=tenant_id,
                account_id=account.id,
                platform=account.platform,
                payload=payload,
                created_by=created_by,
                work_id=work.id if work is not None else None,
            )
        except Exception:
            redis_client.delete(lock_key)
            raise

        try:
            response = self._sau.post_video(
                tenant_id=tenant_id,
                platform=account.platform,  # type: ignore[arg-type]
                sau_account_id=account.sau_account_id,
                video_bytes=video_bytes,
                video_filename=video_filename,
                payload=payload,
                timeout_seconds=dify_config.SAU_PUBLISH_HTTP_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            # Failed dispatch — mark the row failed so the FE shows the error
            # and the single-flight gate releases the account immediately.
            self._tasks.update_terminal(
                task_id=task.id,
                tenant_id=tenant_id,
                status=SocialPublishTaskStatus.FAILED.value,
                error_code=getattr(exc, "code", "sau_api_error"),
                error_message=str(exc)[:4000],
            )
            redis_client.delete(lock_key)
            raise

        updated = self._tasks.attach_sau_task_id(
            task_id=task.id,
            tenant_id=tenant_id,
            sau_task_id=response.sau_task_id,
        )
        # The row is now persisted with status=queued — has_active_for_account
        # will pick it up on the next attempt without depending on the lock.
        redis_client.delete(lock_key)
        return updated or task

    # ----- read -----

    def list_tasks(
        self,
        *,
        tenant_id: str,
        account_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> Sequence[SocialPublishTask]:
        return self._tasks.list_by_tenant(
            tenant_id, account_id=account_id, status=status, limit=limit
        )

    def get_task_status(self, *, task_id: str, tenant_id: str) -> TaskStatusResponse:
        task = self._tasks.get_by_id_and_tenant(task_id, tenant_id)
        if task is None:
            raise TaskNotFoundError(f"task {task_id} not found")

        if not task.is_terminal() and task.sau_task_id:
            task = self._poll_sau(task) or task

        return TaskStatusResponse(
            task=task.to_dict(),
            result={
                "url": task.result_url,
                "error_code": task.error_code,
                "error_message": task.error_message,
            },
        )

    # ----- internals -----

    def _resolve_account(
        self, *, tenant_id: str, account_id: str
    ) -> SocialPublishAccount:
        account = self._accounts.get_by_id_and_tenant(account_id, tenant_id)
        if account is None:
            raise AccountNotFoundError(f"account {account_id} not found")
        return account

    def _resolve_work(
        self, *, tenant_id: str, work_id: str | None
    ) -> CreatorWork | None:
        if work_id is None:
            # Future: support manual uploads where the user attaches an arbitrary
            # video file in the publish drawer. For P2 the publish always
            # originates from a CreatorWork so this branch is unreachable —
            # but keep the typing accurate for the planned extension.
            raise WorkNotFoundError("work_id is required in P2")

        work = db.session.execute(
            db.select(CreatorWork).where(
                CreatorWork.id == work_id,
                CreatorWork.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
        if work is None:
            raise WorkNotFoundError(f"work {work_id} not found")
        return work

    def _validate_payload(self, request: CreateTaskRequest) -> dict[str, Any]:
        title = (request.title or "").strip()
        if not title:
            raise TaskInvalidPayloadError("title is required")
        if len(title) > TITLE_MAX_LEN:
            raise TaskInvalidPayloadError(f"title exceeds {TITLE_MAX_LEN} characters")
        tags = list(request.tags or [])
        if len(tags) > TAGS_MAX_COUNT:
            raise TaskInvalidPayloadError(f"too many tags (max {TAGS_MAX_COUNT})")
        # Strip any leading "#" the user may have typed; the upstream uploader
        # adds them back at the editor level.
        tags = [t.lstrip("#").strip() for t in tags if t and t.strip()]
        desc = (request.desc or "").strip()
        if len(desc) > DESC_MAX_LEN:
            raise TaskInvalidPayloadError(
                f"desc exceeds {DESC_MAX_LEN} characters"
            )
        return {
            "title": title,
            "tags": tags,
            "desc": desc or None,
        }

    def _load_video(self, work: CreatorWork | None) -> tuple[bytes, str]:
        if work is None or not work.file_key:
            raise VideoNotFoundError("work has no file_key")
        try:
            data = storage.load_once(work.file_key)
        except Exception as exc:
            raise VideoNotFoundError(f"failed to load {work.file_key}: {exc}") from exc

        max_bytes = int(dify_config.SOCIAL_PUBLISH_MAX_VIDEO_BYTES)
        if len(data) > max_bytes:
            raise VideoTooLargeError(
                f"video size {len(data)} > limit {max_bytes}"
            )

        # Derive a filename from the storage key so sau can route by extension
        # if it needs to (DouYinVideo just trusts the bytes, but worker tmp
        # files need a stable suffix).
        suffix = work.file_key.rsplit(".", 1)[-1] if "." in work.file_key else "mp4"
        return data, f"{work.id}.{suffix}"

    def _poll_sau(self, task: SocialPublishTask) -> SocialPublishTask | None:
        try:
            snapshot = self._sau.get_task(sau_task_id=task.sau_task_id or "")
        except SauUnreachableError:
            # Transient — keep the row as-is so the next poll tries again.
            return None
        except SauApiError as exc:
            logger.warning(
                "sau /tasks/%s returned %d", task.sau_task_id, exc.status_code
            )
            return None

        state = snapshot.state.upper()
        if state in ("PENDING", "RECEIVED", "RETRY"):
            return None
        if state == "STARTED":
            return self._tasks.update_status_to_running(
                task_id=task.id, tenant_id=task.tenant_id
            )
        if state == "SUCCESS":
            return self._handle_success(task, snapshot.result or {})
        if state == "FAILURE":
            return self._handle_failure(
                task,
                error_code="worker_crashed",
                error_message=str(snapshot.error or "celery task crashed"),
            )
        # Unknown state — leave the row alone, log for ops.
        logger.warning("unknown sau task state %r for %s", state, task.sau_task_id)
        return None

    def _handle_success(
        self, task: SocialPublishTask, result: dict[str, Any]
    ) -> SocialPublishTask | None:
        # Require explicit ``success: True`` — a missing key OR a Celery
        # SUCCESS state with ``result=None`` (which becomes ``{}``) must NOT
        # surface as a publish success. Otherwise a misbehaving worker that
        # forgot to populate the envelope would falsely tell the user their
        # video went live.
        if result.get("success") is True:
            return self._tasks.update_terminal(
                task_id=task.id,
                tenant_id=task.tenant_id,
                status=SocialPublishTaskStatus.SUCCESS.value,
                result_url=result.get("current_url"),
            )
        # The Celery task completed but the upstream publish reported failure
        # — surface it as a Dify-side failure so the FE can show the message.
        upstream_status = str(result.get("status") or "")
        error_code = self._classify_upstream_error(upstream_status)
        if error_code == "cookie_invalid":
            self._mark_account_expired(task.tenant_id, task.account_id)
        return self._handle_failure(
            task,
            error_code=error_code,
            error_message=str(result.get("message") or "")[:4000],
        )

    def _handle_failure(
        self,
        task: SocialPublishTask,
        *,
        error_code: str,
        error_message: str,
    ) -> SocialPublishTask | None:
        return self._tasks.update_terminal(
            task_id=task.id,
            tenant_id=task.tenant_id,
            status=SocialPublishTaskStatus.FAILED.value,
            error_code=error_code,
            error_message=error_message,
        )

    @staticmethod
    def _classify_upstream_error(status: str) -> str:
        if status == "cookie_invalid":
            return "cookie_invalid"
        if status == "timeout":
            return "upload_timeout"
        return "upload_failed"

    def _mark_account_expired(self, tenant_id: str, account_id: str) -> None:
        try:
            self._accounts.update_status(
                account_id=account_id,
                tenant_id=tenant_id,
                status=SocialPublishAccountStatus.EXPIRED.value,
            )
        except Exception:
            logger.exception(
                "failed to mark account %s expired after cookie_invalid",
                account_id,
            )
