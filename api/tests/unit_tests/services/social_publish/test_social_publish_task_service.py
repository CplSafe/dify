"""Service-level tests for SocialPublishTaskService.

Mocks the repos + sau_client + storage. Tenant isolation is enforced
through the account-resolution path; we never trust a request-supplied
account_id without round-tripping through ``get_by_id_and_tenant``.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from models.social_publish import (
    SocialPublishAccount,
    SocialPublishAccountStatus,
    SocialPublishTask,
    SocialPublishTaskStatus,
)
from services.errors.social_publish import (
    AccountExpiredError,
    AccountNotFoundError,
    SauUnreachableError,
    TaskAlreadyInFlightError,
    TaskInvalidPayloadError,
    TaskNotFoundError,
    VideoNotFoundError,
    VideoTooLargeError,
    WorkNotFoundError,
)
from services.sau_client import (
    SauPublishResponse,
    SauTaskStatusResponse,
)
from services.social_publish_task_service import (
    BatchCreateTaskRequest,
    CreateTaskRequest,
    SocialPublishTaskService,
)

# ---------- fixtures ----------


@pytest.fixture
def task_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def account_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def sau() -> MagicMock:
    return MagicMock()


@pytest.fixture
def tier_resolver() -> MagicMock:
    """Default tier mock — every test gets a "mid" tier with plenty of
    headroom. Tests that exercise the quota / priority flows can assign
    ``tier_resolver.get_tier.return_value = TenantTier(...)`` inline."""
    from services.social_publish_tier import TenantTier

    resolver = MagicMock()
    resolver.get_tier.return_value = TenantTier(
        name="mid", concurrent=5, priority=5, max_pending=100
    )
    return resolver


@pytest.fixture
def service(task_repo, account_repo, sau, tier_resolver) -> SocialPublishTaskService:
    # ``count_active_for_tenant`` defaults to 0 so the per-tenant quota
    # check never trips unless the test explicitly raises it.
    task_repo.count_active_for_tenant.return_value = 0
    return SocialPublishTaskService(
        task_repository=task_repo,
        account_repository=account_repo,
        sau_client=sau,
        tier_resolver=tier_resolver,
    )


def _account(
    *,
    id: str = "acc-1",
    tenant_id: str = "tenant-a",
    status: str = SocialPublishAccountStatus.ACTIVE.value,
    platform: str = "douyin",
    sau_account_id: str = "sau-1",
) -> MagicMock:
    a = MagicMock(spec=SocialPublishAccount)
    a.id = id
    a.tenant_id = tenant_id
    a.status = status
    a.platform = platform
    a.sau_account_id = sau_account_id
    return a


def _task(
    *,
    id: str = "task-1",
    tenant_id: str = "tenant-a",
    account_id: str = "acc-1",
    status: str = SocialPublishTaskStatus.PENDING.value,
    sau_task_id: str | None = None,
    result_url: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> MagicMock:
    t = MagicMock(spec=SocialPublishTask)
    t.id = id
    t.tenant_id = tenant_id
    t.account_id = account_id
    t.platform = "douyin"
    t.status = status
    t.sau_task_id = sau_task_id
    t.result_url = result_url
    t.error_code = error_code
    t.error_message = error_message
    t.work_id = None
    t.is_terminal = lambda: status in ("success", "failed")
    t.to_dict = lambda: {
        "id": t.id,
        "account_id": t.account_id,
        "platform": t.platform,
        "status": t.status,
        "result_url": t.result_url,
        "error_code": t.error_code,
        "error_message": t.error_message,
        "created_at": "2026-04-18T00:00:00",
        "updated_at": "2026-04-18T00:00:00",
    }
    return t


@pytest.fixture
def storage_load() -> Any:
    """Patch ext_storage.storage so the multipart path is taken by default.

    Tests that want to exercise the presigned-URL path can override
    ``st.supports_presigned_url.return_value`` and ``st.get_size`` /
    ``st.generate_presigned_url`` inline.
    """
    with patch("services.social_publish_task_service.storage") as st:
        st.load_once = MagicMock(return_value=b"VIDEO BYTES")
        st.supports_presigned_url = MagicMock(return_value=False)
        st.get_size = MagicMock(return_value=None)
        st.generate_presigned_url = MagicMock(return_value="https://signed/url")
        yield st


@pytest.fixture(autouse=True)
def redis_client_mock() -> Any:
    """Patch redis_client so the single-flight lock + tenant quota
    counter both pass through under unit tests.

    Tests that want to assert on the gates can re-bind:
        rc.set.return_value = False                      # blocks single-flight
        rc.register_script.return_value = lambda **kw: 0  # blocks quota
    """
    with patch("services.social_publish_task_service.redis_client") as rc:
        rc.set = MagicMock(return_value=True)
        rc.delete = MagicMock(return_value=1)
        rc.decr = MagicMock(return_value=0)
        # The Lua script object Redis returns is callable via
        # ``script(keys=..., args=...)``. By default we let acquires
        # succeed; tests override per-case.
        script_runner = MagicMock(return_value=1)
        rc.register_script = MagicMock(return_value=script_runner)
        yield rc


@pytest.fixture
def db_session() -> Any:
    """Patch the db.session so the work-resolve path can be exercised
    without a real DB."""
    with patch("services.social_publish_task_service.db") as db:
        yield db


def _make_work_session(db_session, *, work_id: str = "work-1", tenant_id: str = "tenant-a"):
    work = MagicMock()
    work.id = work_id
    work.tenant_id = tenant_id
    work.file_key = "creator_works/x.mp4"
    db_session.session.execute.return_value.scalar_one_or_none.return_value = work
    return work


# ---------- create_task ----------


class TestCreateTask:
    def test_rejects_when_account_missing(self, service, account_repo):
        account_repo.get_by_id_and_tenant.return_value = None
        with pytest.raises(AccountNotFoundError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-x",
                    work_id="work-1",
                    title="hi",
                    tags=[],
                    desc=None,
                ),
            )

    def test_rejects_when_account_expired(self, service, account_repo):
        account_repo.get_by_id_and_tenant.return_value = _account(
            status=SocialPublishAccountStatus.EXPIRED.value
        )
        with pytest.raises(AccountExpiredError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                ),
            )

    def test_rejects_blank_title(self, service, account_repo, db_session, storage_load):
        account_repo.get_by_id_and_tenant.return_value = _account()
        with pytest.raises(TaskInvalidPayloadError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="   ",
                    tags=None,
                    desc=None,
                ),
            )

    def test_rejects_too_many_tags(self, service, account_repo, db_session, storage_load):
        account_repo.get_by_id_and_tenant.return_value = _account()
        with pytest.raises(TaskInvalidPayloadError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=[f"t{i}" for i in range(11)],
                    desc=None,
                ),
            )

    def test_rejects_when_in_flight_task_exists(
        self, service, account_repo, task_repo, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = True
        with pytest.raises(TaskAlreadyInFlightError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                ),
            )

    def test_rejects_video_too_large(
        self, service, account_repo, task_repo, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        # Force the loader to return a giant byte string.
        storage_load.load_once.return_value = b"X" * (200 * 1024 * 1024)
        with pytest.raises(VideoTooLargeError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                ),
            )

    def test_rejects_when_work_missing(
        self, service, account_repo, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account()
        db_session.session.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(WorkNotFoundError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                ),
            )

    def test_rejects_when_work_has_no_file_key(
        self, service, account_repo, task_repo, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account()
        work = _make_work_session(db_session)
        work.file_key = None
        task_repo.has_active_for_account.return_value = False
        with pytest.raises(VideoNotFoundError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                ),
            )

    def test_happy_path_creates_row_then_attaches_sau_id(
        self, service, account_repo, task_repo, sau, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        created = _task()
        task_repo.create.return_value = created
        attached = _task(status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1")
        task_repo.attach_sau_task_id.return_value = attached
        sau.post_video.return_value = SauPublishResponse(sau_task_id="cel-1")

        result = service.create_task(
            tenant_id="tenant-a",
            created_by="u",
            request=CreateTaskRequest(
                account_id="acc-1",
                work_id="work-1",
                title="hi",
                tags=["#美食 ", "  日常"],
                desc="desc",
            ),
        )
        assert result.status == SocialPublishTaskStatus.QUEUED.value
        # Tags get the leading # stripped + whitespace cleaned.
        sent_payload = sau.post_video.call_args.kwargs["payload"]
        assert sent_payload["tags"] == ["美食", "日常"]
        assert sent_payload["title"] == "hi"
        assert sau.post_video.call_args.kwargs["sau_account_id"] == "sau-1"
        # Account id flows from the resolved account, not the request.
        task_repo.create.assert_called_once()

    def test_marks_task_failed_when_sau_dispatch_fails(
        self, service, account_repo, task_repo, sau, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        created = _task()
        task_repo.create.return_value = created
        sau.post_video.side_effect = SauUnreachableError("down")

        with pytest.raises(SauUnreachableError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                ),
            )

        # The row was created and then immediately marked failed so the
        # single-flight gate releases.
        task_repo.update_terminal.assert_called_once()
        kw = task_repo.update_terminal.call_args.kwargs
        assert kw["status"] == SocialPublishTaskStatus.FAILED.value
        assert kw["error_code"] == "sau_unreachable"

    def test_redis_lock_blocks_concurrent_dispatch(
        self,
        service,
        account_repo,
        task_repo,
        sau,
        db_session,
        storage_load,
        redis_client_mock,
    ):
        # Simulate redis SET NX returning False — another request already
        # holds the lock for this (tenant, account).
        redis_client_mock.set.return_value = False
        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)

        with pytest.raises(TaskAlreadyInFlightError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                ),
            )
        # Lock-blocked path must NOT touch the DB or sau.
        task_repo.create.assert_not_called()
        sau.post_video.assert_not_called()
        # Lock release must NOT happen (otherwise we'd let the OTHER holder
        # think they can proceed) — only the holder releases.
        redis_client_mock.delete.assert_not_called()


# ---------- P3: tier / quota / priority ----------


class TestVideoTransport:
    def test_uses_presigned_url_when_supported_and_above_threshold(
        self,
        service,
        account_repo,
        task_repo,
        sau,
        db_session,
        storage_load,
    ):
        from services.sau_client import SauPublishResponse

        # Storage backend supports presigning AND the work file is "large".
        # The threshold default is 5MB; report 10MB so we land on the URL path.
        storage_load.supports_presigned_url.return_value = True
        storage_load.get_size.return_value = 10 * 1024 * 1024
        storage_load.generate_presigned_url.return_value = "https://s3.example/video?sig=x"

        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.return_value = _task()
        task_repo.attach_sau_task_id.return_value = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1"
        )
        sau.post_video.return_value = SauPublishResponse(sau_task_id="cel-1")

        service.create_task(
            tenant_id="tenant-a",
            created_by="u",
            request=CreateTaskRequest(
                account_id="acc-1",
                work_id="work-1",
                title="hi",
                tags=None,
                desc=None,
            ),
        )

        # post_video got the URL, NOT the bytes.
        kw = sau.post_video.call_args.kwargs
        assert kw["video_url"] == "https://s3.example/video?sig=x"
        assert kw["video_bytes"] is None
        # And we never read the bytes through storage.load_once on this path.
        storage_load.load_once.assert_not_called()

    def test_falls_back_to_multipart_when_file_below_threshold(
        self,
        service,
        account_repo,
        task_repo,
        sau,
        db_session,
        storage_load,
    ):
        from services.sau_client import SauPublishResponse

        # Backend supports presigning, but the file is tiny (1MB) so we
        # skip the round-trip overhead and use multipart.
        storage_load.supports_presigned_url.return_value = True
        storage_load.get_size.return_value = 1 * 1024 * 1024

        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.return_value = _task()
        task_repo.attach_sau_task_id.return_value = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1"
        )
        sau.post_video.return_value = SauPublishResponse(sau_task_id="cel-1")

        service.create_task(
            tenant_id="tenant-a",
            created_by="u",
            request=CreateTaskRequest(
                account_id="acc-1",
                work_id="work-1",
                title="hi",
                tags=None,
                desc=None,
            ),
        )

        kw = sau.post_video.call_args.kwargs
        assert kw["video_bytes"] == b"VIDEO BYTES"
        assert kw["video_url"] is None
        # And we never minted a useless presigned URL.
        storage_load.generate_presigned_url.assert_not_called()

    def test_falls_back_to_multipart_when_size_unknown(
        self,
        service,
        account_repo,
        task_repo,
        sau,
        db_session,
        storage_load,
    ):
        from services.sau_client import SauPublishResponse

        # Backend supports presigning but get_size returned None (e.g. the
        # head-object call timed out). Don't gamble on the size — fall back.
        storage_load.supports_presigned_url.return_value = True
        storage_load.get_size.return_value = None

        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.return_value = _task()
        task_repo.attach_sau_task_id.return_value = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1"
        )
        sau.post_video.return_value = SauPublishResponse(sau_task_id="cel-1")

        service.create_task(
            tenant_id="tenant-a",
            created_by="u",
            request=CreateTaskRequest(
                account_id="acc-1",
                work_id="work-1",
                title="hi",
                tags=None,
                desc=None,
            ),
        )

        kw = sau.post_video.call_args.kwargs
        assert kw["video_bytes"] == b"VIDEO BYTES"
        assert kw["video_url"] is None


class TestTierGating:
    def test_rejects_when_tenant_quota_exceeded(
        self,
        service,
        account_repo,
        task_repo,
        tier_resolver,
        db_session,
        storage_load,
        redis_client_mock,
    ):
        from services.errors.social_publish import TaskQuotaExceededError
        from services.social_publish_tier import TenantTier

        account_repo.get_by_id_and_tenant.return_value = _account()
        # Tenant is on the "low" tier (max 50 in-flight). Force the
        # atomic Lua quota acquire to refuse — same shape as the real
        # script returning 0 when n > limit.
        tier_resolver.get_tier.return_value = TenantTier(
            name="low", concurrent=2, priority=1, max_pending=50
        )
        redis_client_mock.register_script.return_value = MagicMock(return_value=0)
        task_repo.count_active_for_tenant.return_value = 50

        with pytest.raises(TaskQuotaExceededError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                ),
            )

        # The quota check must happen BEFORE the single-flight Redis lock,
        # the work resolve and the sau call — so none of those should run.
        task_repo.has_active_for_account.assert_not_called()

    def test_quota_release_on_dispatch_failure(
        self,
        service,
        account_repo,
        task_repo,
        sau,
        tier_resolver,
        db_session,
        storage_load,
        redis_client_mock,
    ):
        """A failed dispatch must DECR the quota counter so a single
        glitch doesn't permanently consume one of the tenant's slots
        until the 10-min TTL kicks in."""
        from services.errors.social_publish import SauUnreachableError

        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.return_value = _task()
        sau.post_video.side_effect = SauUnreachableError("network")

        with pytest.raises(SauUnreachableError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                ),
            )

        # The quota counter MUST have been decremented in the finally
        # block (we asserted post_video failed, so dispatch failed, so
        # ownership stays with this method and finally releases).
        redis_client_mock.decr.assert_called_once()

    def test_high_tier_priority_propagates_to_post_video(
        self,
        service,
        account_repo,
        task_repo,
        sau,
        tier_resolver,
        db_session,
        storage_load,
    ):
        from services.social_publish_tier import TenantTier

        account_repo.get_by_id_and_tenant.return_value = _account()
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.return_value = _task()
        task_repo.attach_sau_task_id.return_value = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-hi"
        )
        tier_resolver.get_tier.return_value = TenantTier(
            name="high", concurrent=10, priority=9, max_pending=200
        )
        from services.sau_client import SauPublishResponse

        sau.post_video.return_value = SauPublishResponse(sau_task_id="cel-hi")

        service.create_task(
            tenant_id="tenant-a",
            created_by="u",
            request=CreateTaskRequest(
                account_id="acc-1",
                work_id="work-1",
                title="hi",
                tags=None,
                desc=None,
            ),
        )

        # priority kw-arg was forwarded from tier.priority.
        assert sau.post_video.call_args.kwargs["priority"] == 9


# ---------- get_task_status ----------


class TestGetTaskStatus:
    def test_raises_for_unknown_task(self, service, task_repo):
        task_repo.get_by_id_and_tenant.return_value = None
        with pytest.raises(TaskNotFoundError):
            service.get_task_status(task_id="t", tenant_id="tenant-a")

    def test_returns_terminal_without_polling_sau(self, service, task_repo, sau):
        task_repo.get_by_id_and_tenant.return_value = _task(
            status=SocialPublishTaskStatus.SUCCESS.value,
            sau_task_id="cel-1",
            result_url="https://x",
        )
        snap = service.get_task_status(task_id="t", tenant_id="tenant-a")
        sau.get_task.assert_not_called()
        assert snap.task["status"] == SocialPublishTaskStatus.SUCCESS.value
        assert snap.result["url"] == "https://x"

    def test_polls_sau_for_pending_task_and_writes_running_state(
        self, service, task_repo, sau
    ):
        running = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1"
        )
        task_repo.get_by_id_and_tenant.return_value = running
        sau.get_task.return_value = SauTaskStatusResponse(
            sau_task_id="cel-1", state="STARTED", result=None, error=None
        )
        task_repo.update_status_to_running.return_value = _task(
            status=SocialPublishTaskStatus.RUNNING.value, sau_task_id="cel-1"
        )

        service.get_task_status(task_id="t", tenant_id="tenant-a")
        task_repo.update_status_to_running.assert_called_once()

    def test_marks_terminal_success_with_result_url(self, service, task_repo, sau):
        task_repo.get_by_id_and_tenant.return_value = _task(
            status=SocialPublishTaskStatus.RUNNING.value, sau_task_id="cel-1"
        )
        sau.get_task.return_value = SauTaskStatusResponse(
            sau_task_id="cel-1",
            state="SUCCESS",
            result={"success": True, "current_url": "https://x"},
            error=None,
        )
        task_repo.update_terminal.return_value = _task(
            status=SocialPublishTaskStatus.SUCCESS.value,
            sau_task_id="cel-1",
            result_url="https://x",
        )
        snap = service.get_task_status(task_id="t", tenant_id="tenant-a")
        assert task_repo.update_terminal.call_args.kwargs["status"] == "success"
        assert snap.result["url"] == "https://x"

    def test_marks_failed_and_expires_account_on_cookie_invalid(
        self, service, task_repo, account_repo, sau
    ):
        task_repo.get_by_id_and_tenant.return_value = _task(
            status=SocialPublishTaskStatus.RUNNING.value, sau_task_id="cel-1"
        )
        sau.get_task.return_value = SauTaskStatusResponse(
            sau_task_id="cel-1",
            state="SUCCESS",
            result={"success": False, "status": "cookie_invalid", "message": "bad"},
            error=None,
        )
        task_repo.update_terminal.return_value = _task(
            status=SocialPublishTaskStatus.FAILED.value, error_code="cookie_invalid"
        )
        service.get_task_status(task_id="t", tenant_id="tenant-a")

        # Account row gets flipped to expired so the FE shows re-auth.
        account_repo.update_status.assert_called_once()
        assert (
            account_repo.update_status.call_args.kwargs["status"]
            == SocialPublishAccountStatus.EXPIRED.value
        )

    def test_celery_success_with_missing_envelope_does_not_fake_success(
        self, service, task_repo, sau
    ):
        # Codex Q6: a Celery SUCCESS state with `result=None` (or missing
        # the `success` key) MUST NOT be reported as a publish success.
        task_repo.get_by_id_and_tenant.return_value = _task(
            status=SocialPublishTaskStatus.RUNNING.value, sau_task_id="cel-1"
        )
        sau.get_task.return_value = SauTaskStatusResponse(
            sau_task_id="cel-1", state="SUCCESS", result=None, error=None
        )
        task_repo.update_terminal.return_value = _task(
            status=SocialPublishTaskStatus.FAILED.value, error_code="upload_failed"
        )
        service.get_task_status(task_id="t", tenant_id="tenant-a")
        kw = task_repo.update_terminal.call_args.kwargs
        assert kw["status"] == SocialPublishTaskStatus.FAILED.value
        # Classified via the upstream-status fallback (which is empty
        # string here → upload_failed).
        assert kw["error_code"] == "upload_failed"

    def test_marks_failed_when_celery_state_is_failure(
        self, service, task_repo, sau
    ):
        task_repo.get_by_id_and_tenant.return_value = _task(
            status=SocialPublishTaskStatus.RUNNING.value, sau_task_id="cel-1"
        )
        sau.get_task.return_value = SauTaskStatusResponse(
            sau_task_id="cel-1", state="FAILURE", result=None, error="boom"
        )
        task_repo.update_terminal.return_value = _task(
            status=SocialPublishTaskStatus.FAILED.value, error_code="worker_crashed"
        )
        service.get_task_status(task_id="t", tenant_id="tenant-a")
        kw = task_repo.update_terminal.call_args.kwargs
        assert kw["error_code"] == "worker_crashed"

    def test_skips_state_change_on_sau_unreachable(
        self, service, task_repo, sau
    ):
        task_repo.get_by_id_and_tenant.return_value = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1"
        )
        sau.get_task.side_effect = SauUnreachableError("network blip")
        # Must not raise — caller should keep polling.
        snap = service.get_task_status(task_id="t", tenant_id="tenant-a")
        assert snap.task["status"] == SocialPublishTaskStatus.QUEUED.value
        task_repo.update_terminal.assert_not_called()


# ---------- P4: platform_payload + batch dispatch ----------


class TestPlatformPayload:
    def test_xhs_location_threaded_into_payload(
        self, service, account_repo, task_repo, sau, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account(platform="xhs")
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.return_value = _task()
        task_repo.attach_sau_task_id.return_value = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1"
        )
        sau.post_video.return_value = SauPublishResponse(sau_task_id="cel-1")

        service.create_task(
            tenant_id="tenant-a",
            created_by="u",
            request=CreateTaskRequest(
                account_id="acc-1",
                work_id="work-1",
                title="hi",
                tags=None,
                desc=None,
                platform_payload={"location": "Shanghai"},
            ),
        )
        sent_payload = sau.post_video.call_args.kwargs["payload"]
        # Allowed key is forwarded under the platform_payload sub-dict so
        # the sau worker's apply_platform_extras can pick it up.
        assert sent_payload["platform_payload"] == {"location": "Shanghai"}

    def test_ks_drops_platform_payload(
        self, service, account_repo, task_repo, sau, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account(platform="ks")
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.return_value = _task()
        task_repo.attach_sau_task_id.return_value = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1"
        )
        sau.post_video.return_value = SauPublishResponse(sau_task_id="cel-1")

        service.create_task(
            tenant_id="tenant-a",
            created_by="u",
            request=CreateTaskRequest(
                account_id="acc-1",
                work_id="work-1",
                title="hi",
                tags=None,
                desc=None,
                # KS uploader has no location support; runner should
                # silently drop, not 400.
                platform_payload={"location": "Shanghai"},
            ),
        )
        sent_payload = sau.post_video.call_args.kwargs["payload"]
        assert "platform_payload" not in sent_payload

    def test_unknown_keys_are_silently_dropped(
        self, service, account_repo, task_repo, sau, db_session, storage_load
    ):
        # A multi-target batch may pass a key relevant to one platform
        # while we're publishing to another — that should not 400.
        account_repo.get_by_id_and_tenant.return_value = _account(platform="douyin")
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.return_value = _task()
        task_repo.attach_sau_task_id.return_value = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1"
        )
        sau.post_video.return_value = SauPublishResponse(sau_task_id="cel-1")

        service.create_task(
            tenant_id="tenant-a",
            created_by="u",
            request=CreateTaskRequest(
                account_id="acc-1",
                work_id="work-1",
                title="hi",
                tags=None,
                desc=None,
                platform_payload={
                    "location": "Beijing",
                    "totally_made_up_field": "ignored",
                },
            ),
        )
        sent_payload = sau.post_video.call_args.kwargs["payload"]
        assert sent_payload["platform_payload"] == {"location": "Beijing"}

    def test_oversize_location_rejected(
        self, service, account_repo, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account(platform="douyin")
        _make_work_session(db_session)
        with pytest.raises(TaskInvalidPayloadError):
            service.create_task(
                tenant_id="tenant-a",
                created_by="u",
                request=CreateTaskRequest(
                    account_id="acc-1",
                    work_id="work-1",
                    title="hi",
                    tags=None,
                    desc=None,
                    platform_payload={"location": "x" * 200},
                ),
            )


class TestBatchDispatch:
    def test_empty_targets_rejected(self, service):
        with pytest.raises(TaskInvalidPayloadError):
            service.create_tasks_batch(
                tenant_id="tenant-a",
                created_by="u",
                work_id="work-1",
                title="hi",
                tags=None,
                desc=None,
                targets=[],
            )

    def test_too_many_targets_rejected(self, service):
        with pytest.raises(TaskInvalidPayloadError):
            service.create_tasks_batch(
                tenant_id="tenant-a",
                created_by="u",
                work_id="work-1",
                title="hi",
                tags=None,
                desc=None,
                targets=[
                    BatchCreateTaskRequest(account_id=f"acc-{i}") for i in range(11)
                ],
            )

    def test_partial_success_is_per_target(
        self, service, account_repo, task_repo, sau, db_session, storage_load
    ):
        accounts = {
            "acc-dy": _account(id="acc-dy", platform="douyin", sau_account_id="sau-dy"),
            "acc-xhs": _account(id="acc-xhs", platform="xhs", sau_account_id="sau-xhs"),
        }
        account_repo.get_by_id_and_tenant.side_effect = lambda aid, _t: accounts.get(aid)
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.side_effect = [_task(id="t-dy"), _task(id="t-xhs")]
        task_repo.attach_sau_task_id.side_effect = [
            _task(id="t-dy", status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-dy"),
            _task(id="t-xhs", status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-xhs"),
        ]
        # First target enqueues fine; second fails at sau.
        sau.post_video.side_effect = [
            SauPublishResponse(sau_task_id="cel-dy"),
            SauUnreachableError("xhs route down"),
        ]

        results = service.create_tasks_batch(
            tenant_id="tenant-a",
            created_by="u",
            work_id="work-1",
            title="hi",
            tags=None,
            desc=None,
            targets=[
                BatchCreateTaskRequest(
                    account_id="acc-dy",
                    platform_payload={"location": "Shanghai"},
                ),
                BatchCreateTaskRequest(
                    account_id="acc-xhs",
                    platform_payload={"location": "Beijing"},
                ),
            ],
        )
        assert len(results) == 2
        assert results[0].account_id == "acc-dy"
        assert results[0].success is True
        assert results[0].task_id == "t-dy"
        assert results[1].account_id == "acc-xhs"
        assert results[1].success is False
        assert "xhs route down" in (results[1].error_message or "")

    def test_duplicate_account_ids_flagged_per_target(
        self, service, account_repo, task_repo, sau, db_session, storage_load
    ):
        account_repo.get_by_id_and_tenant.return_value = _account(platform="douyin")
        _make_work_session(db_session)
        task_repo.has_active_for_account.return_value = False
        task_repo.create.return_value = _task()
        task_repo.attach_sau_task_id.return_value = _task(
            status=SocialPublishTaskStatus.QUEUED.value, sau_task_id="cel-1"
        )
        sau.post_video.return_value = SauPublishResponse(sau_task_id="cel-1")

        results = service.create_tasks_batch(
            tenant_id="tenant-a",
            created_by="u",
            work_id="work-1",
            title="hi",
            tags=None,
            desc=None,
            targets=[
                BatchCreateTaskRequest(account_id="acc-1"),
                BatchCreateTaskRequest(account_id="acc-1"),
            ],
        )
        assert results[0].success is True
        assert results[1].success is False
        assert results[1].error_code == "duplicate_target"
