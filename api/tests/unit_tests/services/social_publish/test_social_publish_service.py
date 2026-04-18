"""Service-level orchestration tests for SocialPublishService.

Verifies tenant-isolation invariants, the QR auth state machine, and the
delete flow — all with mocked repository, sau_client and redis_client.
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from models.social_publish import SocialPublishAccount, SocialPublishAccountStatus
from services.errors.social_publish import (
    AccountNotFoundError,
    PlatformUnsupportedError,
    SauApiError,
    SauUnreachableError,
    SessionExpiredError,
    TenantMismatchError,
)
from services.sau_client import (
    SauLoginInitResponse,
    SauLoginStatusResponse,
)
from services.social_publish_service import (
    AUTH_SESSION_TTL_SECONDS,
    AuthStartResponse,
    AuthStatusResponse,
    SocialPublishService,
)


@pytest.fixture
def repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def sau() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(repo, sau) -> SocialPublishService:
    return SocialPublishService(repository=repo, sau_client=sau)


def _row(*, tenant_id: str = "tenant-a", **overrides: Any) -> SocialPublishAccount:
    """Build a SocialPublishAccount-like mock with the fields the service touches."""
    row = MagicMock(spec=SocialPublishAccount)
    row.id = overrides.get("id", "row-1")
    row.tenant_id = tenant_id
    row.platform = overrides.get("platform", "douyin")
    row.sau_account_id = overrides.get("sau_account_id", "sau-1")
    row.display_name = overrides.get("display_name", "A")
    row.avatar_url = overrides.get("avatar_url")
    row.status = overrides.get("status", SocialPublishAccountStatus.ACTIVE.value)
    row.last_check_at = None
    row.created_at = MagicMock()
    row.created_at.isoformat = lambda: "2026-04-18T00:00:00"
    row.to_dict = lambda: {
        "id": row.id,
        "platform": row.platform,
        "display_name": row.display_name,
        "avatar_url": row.avatar_url,
        "status": row.status,
        "last_check_at": None,
        "created_at": "2026-04-18T00:00:00",
    }
    return row


# ---------- get_account / list_accounts ----------


class TestGetAccount:
    def test_returns_row_when_repository_finds_it(self, service, repo):
        repo.get_by_id_and_tenant.return_value = _row()
        result = service.get_account(account_id="row-1", tenant_id="tenant-a")
        assert result.id == "row-1"

    def test_raises_account_not_found_when_repository_returns_none(
        self, service, repo
    ):
        repo.get_by_id_and_tenant.return_value = None
        with pytest.raises(AccountNotFoundError):
            service.get_account(account_id="row-1", tenant_id="tenant-a")


# ---------- start_auth ----------


class TestStartAuth:
    def test_rejects_unsupported_platform(self, service):
        # P4: ks doesn't have an upstream cookie_gen yet; xhs is now
        # supported alongside douyin.
        with pytest.raises(PlatformUnsupportedError):
            service.start_auth(
                tenant_id="t",
                platform="ks",
                account_id=None,
                created_by="u",
            )

    def test_writes_session_to_redis_with_ttl_then_returns_qr(self, service, repo, sau):
        sau.start_login.return_value = SauLoginInitResponse(
            qr_image_base64="data:image/png;base64,FAKE",
            expires_in=180,
        )
        with patch("services.social_publish_service.redis_client") as redis:
            result = service.start_auth(
                tenant_id="tenant-a",
                platform="douyin",
                account_id=None,
                created_by="user-1",
            )

        assert isinstance(result, AuthStartResponse)
        assert result.qr_image_base64 == "data:image/png;base64,FAKE"
        assert result.expires_in == 180
        # The session must have been persisted with the auth-session TTL.
        redis.setex.assert_called_once()
        args, _ = redis.setex.call_args
        assert args[0].startswith("sau:auth:")
        assert args[1] == AUTH_SESSION_TTL_SECONDS
        payload = json.loads(args[2])
        assert payload["tenant_id"] == "tenant-a"
        assert payload["status"] == "waiting"

    def test_reauth_propagates_sau_account_id_after_ownership_check(
        self, service, repo, sau
    ):
        existing = _row(sau_account_id="sau-existing")
        repo.get_by_id_and_tenant.return_value = existing
        sau.start_login.return_value = SauLoginInitResponse(
            qr_image_base64="data:image/png;base64,FAKE", expires_in=120
        )

        with patch("services.social_publish_service.redis_client"):
            service.start_auth(
                tenant_id="tenant-a",
                platform="douyin",
                account_id=existing.id,
                created_by="user-1",
            )

        # Service must look up the row scoped to tenant_id (not by id alone).
        repo.get_by_id_and_tenant.assert_called_once_with(existing.id, "tenant-a")
        # And forward the resolved sau_account_id to sau, not the dify row id.
        sau.start_login.assert_called_once()
        kwargs = sau.start_login.call_args.kwargs
        assert kwargs["sau_account_id"] == "sau-existing"

    def test_clears_session_when_sau_call_fails(self, service, repo, sau):
        sau.start_login.side_effect = SauUnreachableError("no route")
        with patch("services.social_publish_service.redis_client") as redis:
            with pytest.raises(SauUnreachableError):
                service.start_auth(
                    tenant_id="tenant-a",
                    platform="douyin",
                    account_id=None,
                    created_by="user-1",
                )
        # Failed start ⇒ tear down so the user can retry without waiting TTL.
        redis.delete.assert_called_once()


# ---------- get_auth_status ----------


def _make_session(tenant_id: str = "tenant-a", status: str = "waiting", **extra: Any) -> dict:
    return {
        "tenant_id": tenant_id,
        "platform": "douyin",
        "status": status,
        "sau_account_id": extra.get("sau_account_id"),
        "account_id": extra.get("account_id"),
        "created_by": extra.get("created_by", "user-1"),
        "profile": extra.get("profile"),
        "updated_at": "2026-04-18T00:00:00",
        **{k: v for k, v in extra.items() if k not in {"sau_account_id", "account_id", "created_by", "profile"}},
    }


class TestGetAuthStatus:
    def test_raises_when_session_missing(self, service):
        with patch("services.social_publish_service.redis_client") as redis:
            redis.get.return_value = None
            with pytest.raises(SessionExpiredError):
                service.get_auth_status(session_id="s1", tenant_id="tenant-a")

    def test_raises_tenant_mismatch_when_caller_tenant_does_not_match_session(
        self, service
    ):
        with patch("services.social_publish_service.redis_client") as redis:
            redis.get.return_value = json.dumps(_make_session(tenant_id="tenant-a"))
            with pytest.raises(TenantMismatchError):
                service.get_auth_status(session_id="s1", tenant_id="tenant-b")

    def test_refreshes_from_sau_for_non_terminal_status(self, service, sau):
        sau.get_login_status.return_value = SauLoginStatusResponse(
            status="scanned",
            sau_account_id=None,
            profile=None,
            message=None,
        )
        with patch("services.social_publish_service.redis_client") as redis:
            redis.get.return_value = json.dumps(_make_session(status="waiting"))
            result = service.get_auth_status(session_id="s1", tenant_id="tenant-a")
        assert isinstance(result, AuthStatusResponse)
        sau.get_login_status.assert_called_once_with(session_id="s1")
        # Session got rewritten with the fresh status.
        assert redis.setex.called

    def test_creates_account_on_first_success_and_caches_dict(self, service, repo, sau):
        # Seed the session as already-success so we exercise the reconcile
        # branch without depending on stateful redis.setex/get coordination.
        repo.get_by_sau_account_id.return_value = None
        created = _row(sau_account_id="sau-new", display_name="小妹", status="active")
        repo.create.return_value = created

        with patch("services.social_publish_service.redis_client") as redis:
            redis.get.return_value = json.dumps(
                _make_session(
                    status="success",
                    sau_account_id="sau-new",
                    profile={"display_name": "小妹", "avatar_url": "https://x"},
                    created_by="user-1",
                )
            )
            result = service.get_auth_status(session_id="s1", tenant_id="tenant-a")

        repo.create.assert_called_once()
        # last_check_at update must follow with the same tenant scoping.
        repo.update_status.assert_called_once()
        assert result.account is not None
        assert result.account["display_name"] == "小妹"

    def test_replays_cached_account_on_subsequent_success_polls(self, service, repo, sau):
        cached = {"id": "row-1", "display_name": "小妹"}
        with patch("services.social_publish_service.redis_client") as redis:
            redis.get.return_value = json.dumps(
                _make_session(status="success", reconciled_account=cached)
            )
            result = service.get_auth_status(session_id="s1", tenant_id="tenant-a")

        # Cached → no DB writes, no sau call.
        repo.create.assert_not_called()
        repo.update_status.assert_not_called()
        sau.get_login_status.assert_not_called()
        assert result.account == cached

    def test_rejects_when_existing_sau_account_id_belongs_to_other_tenant(
        self, service, repo, sau
    ):
        # Repository says: this sau_account_id is owned by tenant-b.
        repo.get_by_sau_account_id.return_value = _row(
            tenant_id="tenant-b", sau_account_id="sau-shared"
        )
        with patch("services.social_publish_service.redis_client") as redis:
            redis.get.return_value = json.dumps(
                _make_session(
                    tenant_id="tenant-a",
                    status="success",
                    sau_account_id="sau-shared",
                    profile={"display_name": "x", "avatar_url": None},
                )
            )
            with pytest.raises(SauApiError):
                service.get_auth_status(session_id="s1", tenant_id="tenant-a")


# ---------- delete_account ----------


class TestDeleteAccount:
    def test_calls_sau_then_repository_with_tenant_scope(self, service, repo, sau):
        repo.get_by_id_and_tenant.return_value = _row(sau_account_id="sau-1")
        repo.delete_by_id_and_tenant.return_value = True

        service.delete_account(account_id="row-1", tenant_id="tenant-a")

        sau.delete_account.assert_called_once_with(
            tenant_id="tenant-a",
            platform="douyin",
            sau_account_id="sau-1",
        )
        repo.delete_by_id_and_tenant.assert_called_once_with("row-1", "tenant-a")

    def test_swallows_sau_failure_and_still_deletes_local_row(self, service, repo, sau):
        repo.get_by_id_and_tenant.return_value = _row(sau_account_id="sau-1")
        repo.delete_by_id_and_tenant.return_value = True
        sau.delete_account.side_effect = SauUnreachableError("down")

        service.delete_account(account_id="row-1", tenant_id="tenant-a")

        repo.delete_by_id_and_tenant.assert_called_once()

    def test_raises_tenant_mismatch_when_repository_reports_no_rows_deleted(
        self, service, repo, sau
    ):
        repo.get_by_id_and_tenant.return_value = _row(sau_account_id="sau-1")
        repo.delete_by_id_and_tenant.return_value = False

        with pytest.raises(TenantMismatchError):
            service.delete_account(account_id="row-1", tenant_id="tenant-a")
