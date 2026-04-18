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
    TaskQuotaExceededError,
    VideoNotFoundError,
    VideoTooLargeError,
    WorkNotFoundError,
)
from services.sau_client import SauClient
from services.social_publish_tier import TierResolver

logger = logging.getLogger(__name__)

# Publish-dispatch allowlist. P5: KS dropped entirely — upstream
# social-auto-upload never shipped a ks_cookie_gen, so the auth flow
# can't complete and the publish flow would fast-fail at cookie load.
# The SocialPublishPlatform.KS enum value stays in the model layer so
# old DB rows (if any) can still be read; the cleanup migration
# 2026_04_19_xxxx-remove_ks_social_publish_data deletes them.
SUPPORTED_PLATFORMS_P2 = ("douyin", "xhs")
TITLE_MAX_LEN = 200
DESC_MAX_LEN = 2000
TAGS_MAX_COUNT = 10
LOCATION_MAX_LEN = 80
# Per-platform allowlist of platform_payload keys. Anything outside this
# set is dropped during validation rather than blindly forwarded — keeps
# the FE from injecting fields the sau worker doesn't know about, and
# avoids accidentally leaking internal flags into upstream uploaders.
_PLATFORM_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "douyin": frozenset({"location"}),
    "xhs": frozenset({"location"}),
}

# Single-flight Redis lock TTL — covers the worst-case time between the
# initial check and the persisted attach_sau_task_id. The downstream
# Celery task itself takes much longer; the lock only guards the
# enqueue race, so this short TTL is fine.
SINGLE_FLIGHT_LOCK_TTL_SECONDS = 60

# P3 quota counter TTL — the ``sau:quota:tenant:{id}`` counter exists
# only to make the ``count_active_for_tenant`` check race-free under
# concurrent dispatches. The DB row is the source of truth; this is a
# short-lived advisory key that auto-heals via TTL if a worker crashes
# between INCR and DECR.
QUOTA_COUNTER_TTL_SECONDS = 600


def _single_flight_lock_key(tenant_id: str, account_id: str) -> str:
    return f"sau:publish:single_flight:{tenant_id}:{account_id}"


def _quota_counter_key(tenant_id: str) -> str:
    return f"sau:publish:tenant_quota:{tenant_id}"


# Lua script: atomically INCR the quota counter and back out if we'd
# exceed the cap. Mirrors apps/sau_worker/concurrency.py — same pattern,
# same crash recovery via EXPIRE.
_QUOTA_ACQUIRE_LUA = """
local n = redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
if n > tonumber(ARGV[1]) then
  redis.call('DECR', KEYS[1])
  return 0
end
return n
"""


# ---------- DTOs ----------


@dataclass(frozen=True)
class CreateTaskRequest:
    account_id: str
    work_id: str | None
    title: str
    tags: list[str] | None
    desc: str | None
    # P4: per-platform extras (e.g. ``{"location": "Shanghai"}`` for
    # douyin/xhs). Keys outside the per-platform allowlist are silently
    # dropped during validation. ``None`` is equivalent to ``{}``.
    platform_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class BatchCreateTaskRequest:
    """Per-account spec for ``create_tasks_batch``.

    The shared content (title/tags/desc/work_id) is identical to
    ``CreateTaskRequest``; ``account_id`` and ``platform_payload`` vary
    per-platform so the FE can e.g. publish the same video to a douyin
    account with one location and an xhs account with another."""

    account_id: str
    platform_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class BatchCreateResultItem:
    account_id: str
    success: bool
    task_id: str | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True)
class TaskStatusResponse:
    task: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class _VideoTransport:
    """How to ship the video to sau for a given task.

    Exactly one of ``video_bytes`` or ``video_url`` is set. The presigned
    URL path is preferred for files larger than
    ``SOCIAL_PUBLISH_PRESIGNED_THRESHOLD_BYTES`` when the storage backend
    supports it; everything else falls back to multipart.
    """

    video_bytes: bytes | None
    video_filename: str | None
    video_url: str | None


# ---------- Service ----------


class SocialPublishTaskService:
    def __init__(
        self,
        *,
        task_repository: SocialPublishTaskRepository,
        account_repository: SocialPublishAccountRepository,
        sau_client: SauClient,
        tier_resolver: TierResolver | None = None,
    ) -> None:
        self._tasks = task_repository
        self._accounts = account_repository
        self._sau = sau_client
        # ``TierResolver`` is constructed lazily so unit tests that only
        # exercise the per-account flows don't need to mock the cache.
        self._tier_resolver = tier_resolver or TierResolver()

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

        # P3 quota: cap a tenant's max in-flight tasks based on their tier
        # so a single big workspace can't fill the queue at the expense of
        # everyone else. Done BEFORE the single-flight lock so the 429
        # surfaces immediately rather than after a wasted Redis round-trip.
        #
        # The check uses an atomic INCR-with-cap Lua script so two
        # concurrent requests at exactly the cap can't both pass through;
        # the loser gets a 429. The counter is reconciled with the DB
        # source of truth on every dispatch (see ``_seed_quota_counter``)
        # so it self-heals if a worker crashes between INCR and the
        # eventual DECR (TTL: 10min).
        tier = self._tier_resolver.get_tier(tenant_id)
        if not self._acquire_quota_slot(tenant_id, tier.max_pending):
            active_count = self._tasks.count_active_for_tenant(tenant_id)
            raise TaskQuotaExceededError(
                f"tenant has {active_count} in-flight tasks "
                f"(tier {tier.name} max {tier.max_pending})"
            )
        # From here, every dispatch failure MUST release the quota slot so a
        # failed dispatch doesn't leak a slot for ``QUOTA_COUNTER_TTL``.
        # The slot stays held when dispatch succeeds — the corresponding
        # DB row is in an active status, and the slot is released by
        # ``_release_quota_slot`` from the polling path that flips the row
        # terminal (see ``get_task_status``).
        quota_slot_held = True
        try:
            payload = self._validate_payload(request, platform=account.platform)
            work = self._resolve_work(tenant_id=tenant_id, work_id=request.work_id)
            transport = self._resolve_video_transport(work)

            # Atomic single-flight: take a Redis SET NX lock keyed by
            # (tenant, account) BEFORE the DB check, so two concurrent
            # requests from the same workspace can't both pass the
            # has_active_for_account gate. The lock is released after
            # dispatch succeeds (the row is now persisted with
            # status=queued, and has_active_for_account picks it up on the
            # next attempt).
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
                    payload=payload,
                    # P3: priority is derived from the tenant's tier — FE
                    # never supplies it. sau passes it straight to Celery
                    # so high-tier tasks jump the queue. tier_concurrent
                    # flows to the worker so the per-tenant concurrency
                    # gate uses the right cap.
                    priority=tier.priority,
                    tier_concurrent=tier.concurrent,
                    video_bytes=transport.video_bytes,
                    video_filename=transport.video_filename,
                    video_url=transport.video_url,
                    timeout_seconds=dify_config.SAU_PUBLISH_HTTP_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                # Failed dispatch — mark the row failed so the FE shows
                # the error and the single-flight + quota gates release.
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
            quota_slot_held = False  # ownership transferred to the active row
            return updated or task
        finally:
            if quota_slot_held:
                self._release_quota_slot(tenant_id)

    # ----- batch -----

    def create_tasks_batch(
        self,
        *,
        tenant_id: str,
        created_by: str,
        work_id: str | None,
        title: str,
        tags: list[str] | None,
        desc: str | None,
        targets: list[BatchCreateTaskRequest],
    ) -> list[BatchCreateResultItem]:
        """Dispatch the same content to multiple accounts in one call.

        Each target is dispatched independently — a failure on account A
        doesn't abort accounts B, C, etc. The caller gets a per-target
        result so the FE can render which targets succeeded and which
        need a retry. Single-flight, quota and tier gates run per-target
        the same way as ``create_task`` so behaviour stays identical.
        """
        if not targets:
            raise TaskInvalidPayloadError("at least one target account is required")
        if len(targets) > 10:
            # Soft cap so a single batch can't burn through a tenant's
            # quota in one shot. The DB already enforces the per-tenant
            # ceiling but failing fast at the API edge is friendlier.
            raise TaskInvalidPayloadError("batch dispatch is capped at 10 targets")
        seen_account_ids: set[str] = set()
        results: list[BatchCreateResultItem] = []
        for target in targets:
            if target.account_id in seen_account_ids:
                results.append(
                    BatchCreateResultItem(
                        account_id=target.account_id,
                        success=False,
                        task_id=None,
                        error_code="duplicate_target",
                        error_message="account_id appears more than once in batch",
                    )
                )
                continue
            seen_account_ids.add(target.account_id)
            single = CreateTaskRequest(
                account_id=target.account_id,
                work_id=work_id,
                title=title,
                tags=tags,
                desc=desc,
                platform_payload=target.platform_payload,
            )
            try:
                task = self.create_task(
                    tenant_id=tenant_id,
                    created_by=created_by,
                    request=single,
                )
            except Exception as exc:
                results.append(
                    BatchCreateResultItem(
                        account_id=target.account_id,
                        success=False,
                        task_id=None,
                        error_code=getattr(exc, "code", type(exc).__name__),
                        error_message=str(exc)[:500],
                    )
                )
                continue
            results.append(
                BatchCreateResultItem(
                    account_id=target.account_id,
                    success=True,
                    task_id=task.id,
                    error_code=None,
                    error_message=None,
                )
            )
        return results

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

    def _validate_payload(
        self, request: CreateTaskRequest, *, platform: str
    ) -> dict[str, Any]:
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
        payload: dict[str, Any] = {
            "title": title,
            "tags": tags,
            "desc": desc or None,
        }
        platform_payload = self._validate_platform_payload(
            platform=platform,
            raw=request.platform_payload,
        )
        if platform_payload:
            payload["platform_payload"] = platform_payload
        return payload

    def _validate_platform_payload(
        self, *, platform: str, raw: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Filter platform_payload to the per-platform allowlist + validate
        the value shape. Unknown keys are silently dropped (rather than
        rejected) so a multi-platform batch dispatch doesn't fail just
        because the user filled in a douyin-only field while also
        publishing to ks."""
        if not raw:
            return {}
        allowed = _PLATFORM_PAYLOAD_KEYS.get(platform, frozenset())
        if not allowed:
            return {}
        cleaned: dict[str, Any] = {}
        for key in allowed:
            value = raw.get(key)
            if value is None:
                continue
            if key == "location":
                location = str(value).strip()
                if not location:
                    continue
                if len(location) > LOCATION_MAX_LEN:
                    raise TaskInvalidPayloadError(
                        f"location exceeds {LOCATION_MAX_LEN} characters"
                    )
                cleaned["location"] = location
        return cleaned

    def _resolve_video_transport(self, work: CreatorWork | None) -> _VideoTransport:
        """Pick presigned URL vs multipart for the work's video.

        Decision tree:
        1. work missing file_key → ``VideoNotFoundError`` (consistent with
           the P2 behaviour).
        2. presigning disabled (``SOCIAL_PUBLISH_PREFER_PRESIGNED=False``)
           OR backend doesn't support it → multipart.
        3. backend supports it AND we can cheaply read the size AND the
           file is bigger than ``SOCIAL_PUBLISH_PRESIGNED_THRESHOLD_BYTES``
           → presigned URL (bypasses the multipart byte cap).
        4. backend supports it but the size is unknown / small → multipart
           (the round-trip overhead of a separate sau download isn't worth
           it for tiny clips).
        """
        if work is None or not work.file_key:
            raise VideoNotFoundError("work has no file_key")

        threshold = int(dify_config.SOCIAL_PUBLISH_PRESIGNED_THRESHOLD_BYTES)
        if dify_config.SOCIAL_PUBLISH_PREFER_PRESIGNED and storage.supports_presigned_url():
            try:
                size = storage.get_size(work.file_key)
            except Exception:
                logger.exception(
                    "storage.get_size failed for %s; falling back to multipart",
                    work.file_key,
                )
                size = None
            if size is not None and size >= threshold:
                try:
                    url = storage.generate_presigned_url(
                        work.file_key,
                        expires_in=int(dify_config.SOCIAL_PUBLISH_PRESIGNED_TTL_SECONDS),
                    )
                except Exception as exc:
                    raise VideoNotFoundError(
                        f"failed to presign {work.file_key}: {exc}"
                    ) from exc
                logger.info(
                    "publish using presigned URL",
                    extra={"file_key": work.file_key, "size": size},
                )
                return _VideoTransport(
                    video_bytes=None, video_filename=None, video_url=url
                )

        return self._load_video_multipart(work)

    def _load_video_multipart(self, work: CreatorWork) -> _VideoTransport:
        try:
            data = storage.load_once(work.file_key or "")
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
        file_key = work.file_key or ""
        suffix = file_key.rsplit(".", 1)[-1] if "." in file_key else "mp4"
        return _VideoTransport(
            video_bytes=data,
            video_filename=f"{work.id}.{suffix}",
            video_url=None,
        )

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
            return self._terminal_transition(
                task,
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
        return self._terminal_transition(
            task,
            status=SocialPublishTaskStatus.FAILED.value,
            error_code=error_code,
            error_message=error_message,
        )

    def _terminal_transition(
        self,
        task: SocialPublishTask,
        *,
        status: str,
        result_url: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> SocialPublishTask | None:
        """Wrap ``update_terminal`` with the per-tenant quota release.

        ``update_terminal`` is idempotent — repeated polls of an already
        terminal row no-op. We only release the slot when this call is
        the one that actually flipped the row, which we detect by
        checking the pre-update status.
        """
        was_active = not task.is_terminal()
        updated = self._tasks.update_terminal(
            task_id=task.id,
            tenant_id=task.tenant_id,
            status=status,
            result_url=result_url,
            error_code=error_code,
            error_message=error_message,
        )
        if was_active and updated is not None and updated.is_terminal():
            self._release_quota_slot(task.tenant_id)
        return updated

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

    def _acquire_quota_slot(self, tenant_id: str, max_pending: int) -> bool:
        """Atomically reserve one quota slot for the tenant.

        Uses a Redis Lua script so two concurrent dispatches at exactly
        the cap can't both squeeze through. Returns True on success.
        Returns False when the cap is already full — the caller surfaces
        ``TaskQuotaExceededError`` and the counter is already rolled back
        by the script.
        """
        try:
            script = redis_client.register_script(_QUOTA_ACQUIRE_LUA)
            result = script(
                keys=[_quota_counter_key(tenant_id)],
                args=[int(max_pending), QUOTA_COUNTER_TTL_SECONDS],
            )
            return bool(int(result))
        except Exception:
            # Redis hiccup — fall back to the DB-only check so we don't
            # block dispatches under a transient outage. The fallback
            # exposes the (small) original race the design doc accepted.
            logger.exception("quota slot acquire failed; degraded to DB-only check")
            active = self._tasks.count_active_for_tenant(tenant_id)
            return active < max_pending

    def _release_quota_slot(self, tenant_id: str) -> None:
        """Decrement the quota counter. Best-effort — TTL self-heals."""
        try:
            new_value = int(redis_client.decr(_quota_counter_key(tenant_id)))
        except Exception:
            logger.exception("quota slot release failed for tenant %s", tenant_id)
            return
        if new_value < 0:
            # Defensive: a stray release shouldn't drive the counter
            # negative (which would let later acquires falsely think
            # there's headroom). Reset to 0 with the standard TTL.
            redis_client.set(
                _quota_counter_key(tenant_id), 0, ex=QUOTA_COUNTER_TTL_SECONDS
            )
