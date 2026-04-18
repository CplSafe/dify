"""SocialPublishService — orchestration between Dify, sau, and Redis sessions.

Tenant isolation rules baked into this layer:

- Every read of a single account passes ``tenant_id`` to the repository so
  the SQL ``WHERE`` rejects cross-tenant access at the data-layer.
- Every Redis ``sau:auth:`` session record carries the originating tenant_id;
  ``get_auth_status`` rejects any caller whose tenant_id does not match.
- The single tenant-blind path (``repo.get_by_sau_account_id``) is only used
  during sau-callback reconciliation and immediately re-validates the tenant
  against the Redis session.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from extensions.ext_redis import redis_client
from models.social_publish import (
    SocialPublishAccount,
    SocialPublishAccountStatus,
    SocialPublishPlatform,
)
from repositories.social_publish_account_repository import (
    SocialPublishAccountRepository,
)
from services.errors.social_publish import (
    AccountNotFoundError,
    PlatformUnsupportedError,
    SauApiError,
    SessionExpiredError,
    TenantMismatchError,
)
from services.sau_client import SauClient

logger = logging.getLogger(__name__)

AUTH_SESSION_TTL_SECONDS = 200  # 180s wait + 20s buffer for the last poll
QR_VALID_SECONDS = 180

AuthStatus = Literal["waiting", "scanned", "success", "expired", "failed"]
SUPPORTED_PLATFORMS_P1 = (SocialPublishPlatform.DOUYIN.value,)


# ---------- DTOs ----------


@dataclass(frozen=True)
class AuthStartResponse:
    session_id: str
    qr_image_base64: str
    expires_in: int


@dataclass(frozen=True)
class AuthStatusResponse:
    status: AuthStatus
    account: dict | None
    message: str | None


# ---------- Service ----------


class SocialPublishService:
    """Account-management orchestration layer for the publish-center."""

    def __init__(
        self,
        *,
        repository: SocialPublishAccountRepository,
        sau_client: SauClient,
    ) -> None:
        self._repo = repository
        self._sau = sau_client

    # ----- account read -----

    def list_accounts(
        self,
        *,
        tenant_id: str,
        platform: str | None = None,
    ) -> Sequence[SocialPublishAccount]:
        return self._repo.list_by_tenant(tenant_id, platform=platform)

    def get_account(
        self,
        *,
        account_id: str,
        tenant_id: str,
    ) -> SocialPublishAccount:
        row = self._repo.get_by_id_and_tenant(account_id, tenant_id)
        if row is None:
            raise AccountNotFoundError(f"account {account_id} not found")
        return row

    # ----- QR auth -----

    def start_auth(
        self,
        *,
        tenant_id: str,
        platform: str,
        account_id: str | None,
        created_by: str,
    ) -> AuthStartResponse:
        """Initiate a sau scan-to-auth session.

        ``account_id`` is set when the user is re-authorising an existing row
        (status flips from EXPIRED back to ACTIVE on success). Otherwise a
        brand-new account row is created on the success callback.
        """
        if platform not in SUPPORTED_PLATFORMS_P1:
            raise PlatformUnsupportedError(
                f"platform {platform!r} is not supported in P1"
            )

        # When re-authorising, validate ownership upfront so we can pass the
        # sau_account_id straight through to sau (cookie path locator).
        sau_account_id: str | None = None
        if account_id is not None:
            existing = self.get_account(account_id=account_id, tenant_id=tenant_id)
            sau_account_id = existing.sau_account_id

        session_id = str(uuid.uuid4())
        self._write_session(
            session_id=session_id,
            payload={
                "tenant_id": tenant_id,
                "platform": platform,
                "status": "waiting",
                "sau_account_id": sau_account_id,
                "account_id": account_id,
                "created_by": created_by,
                "profile": None,
                "updated_at": _utcnow_iso(),
            },
        )

        try:
            init = self._sau.start_login(
                tenant_id=tenant_id,
                platform=platform,  # type: ignore[arg-type]
                session_id=session_id,
                sau_account_id=sau_account_id,
            )
        except Exception:
            # Failed to talk to sau → tear down the session so the user can
            # retry without waiting for the TTL.
            redis_client.delete(_session_key(session_id))
            raise

        return AuthStartResponse(
            session_id=session_id,
            qr_image_base64=init.qr_image_base64,
            expires_in=min(init.expires_in or QR_VALID_SECONDS, QR_VALID_SECONDS),
        )

    def get_auth_status(
        self,
        *,
        session_id: str,
        tenant_id: str,
    ) -> AuthStatusResponse:
        session = self._read_session(session_id)
        if session is None:
            raise SessionExpiredError(f"session {session_id} expired or unknown")

        if session["tenant_id"] != tenant_id:
            # Defence-in-depth: shouldn't happen if the controller is correct,
            # but never trust the caller for this kind of cross-tenant probe.
            raise TenantMismatchError("session belongs to a different tenant")

        terminal = session["status"] in ("success", "expired", "failed")
        if not terminal:
            self._refresh_session_from_sau(session_id, session)
            session = self._read_session(session_id) or session

        account_dict: dict | None = None
        if session["status"] == "success":
            cached = session.get("reconciled_account")
            if isinstance(cached, dict):
                # Idempotency: subsequent polls within TTL replay the cached
                # account dict rather than re-running the DB reconcile path.
                account_dict = cached
            else:
                account_dict = self._reconcile_success(session)
                if account_dict is not None:
                    session["reconciled_account"] = account_dict
                    self._write_session(session_id=session_id, payload=session)

        return AuthStatusResponse(
            status=session["status"],
            account=account_dict,
            message=session.get("message"),
        )

    # ----- account delete -----

    def delete_account(self, *, account_id: str, tenant_id: str) -> None:
        row = self.get_account(account_id=account_id, tenant_id=tenant_id)

        # Best-effort: tell sau to drop the cookie. Failure here must not block
        # the local clean-up — operators can run a sweeper later.
        try:
            self._sau.delete_account(
                tenant_id=tenant_id,
                platform=row.platform,  # type: ignore[arg-type]
                sau_account_id=row.sau_account_id,
            )
        except Exception as exc:
            logger.warning(
                "sau delete_account failed; continuing with local delete",
                extra={
                    "tenant_id": tenant_id,
                    "account_id": account_id,
                    "sau_account_id": row.sau_account_id,
                    "error": str(exc),
                },
            )

        if not self._repo.delete_by_id_and_tenant(account_id, tenant_id):
            raise TenantMismatchError("account vanished mid-delete or not yours")

    # ---------- internals ----------

    def _refresh_session_from_sau(self, session_id: str, session: dict) -> None:
        try:
            status = self._sau.get_login_status(session_id=session_id)
        except Exception as exc:
            logger.info(
                "sau get_login_status failed; keeping prior session state",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return

        session["status"] = status.status
        session["sau_account_id"] = status.sau_account_id or session.get("sau_account_id")
        session["profile"] = (
            {
                "display_name": status.profile.display_name,
                "avatar_url": status.profile.avatar_url,
            }
            if status.profile is not None
            else session.get("profile")
        )
        session["message"] = status.message
        session["updated_at"] = _utcnow_iso()
        self._write_session(session_id=session_id, payload=session)

    def _reconcile_success(self, session: dict) -> dict | None:
        sau_account_id = session.get("sau_account_id")
        if not sau_account_id:
            logger.warning(
                "session in success state without sau_account_id; cannot reconcile",
                extra={"session": _redact_session(session)},
            )
            return None

        tenant_id = session["tenant_id"]
        platform = session["platform"]
        profile = session.get("profile") or {}

        existing = self._repo.get_by_sau_account_id(sau_account_id)
        if existing is not None:
            # The sau_account_id has a global UNIQUE constraint, so any prior
            # row must belong to the *same* tenant — reject otherwise.
            if existing.tenant_id != tenant_id:
                raise SauApiError(
                    409,
                    f"sau_account_id {sau_account_id} already bound to a different tenant",
                )
            updated = self._repo.update_status(
                account_id=existing.id,
                tenant_id=tenant_id,
                status=SocialPublishAccountStatus.ACTIVE.value,
                last_check_at=datetime.now(UTC),
                display_name=profile.get("display_name"),
                avatar_url=profile.get("avatar_url"),
            )
            return updated.to_dict() if updated is not None else existing.to_dict()

        created = self._repo.create(
            tenant_id=tenant_id,
            platform=platform,
            sau_account_id=sau_account_id,
            display_name=profile.get("display_name"),
            avatar_url=profile.get("avatar_url"),
            status=SocialPublishAccountStatus.ACTIVE.value,
            created_by=session["created_by"],
        )
        # Persist last_check_at separately so the row reflects the success ping.
        self._repo.update_status(
            account_id=created.id,
            tenant_id=tenant_id,
            status=SocialPublishAccountStatus.ACTIVE.value,
            last_check_at=datetime.now(UTC),
        )
        return created.to_dict()

    def _write_session(self, *, session_id: str, payload: dict) -> None:
        redis_client.setex(
            _session_key(session_id),
            AUTH_SESSION_TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )

    def _read_session(self, session_id: str) -> dict | None:
        raw = redis_client.get(_session_key(session_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.exception("corrupt sau auth session payload; deleting", extra={"session_id": session_id})
            redis_client.delete(_session_key(session_id))
            return None


# ---------- module helpers ----------


def _session_key(session_id: str) -> str:
    return f"sau:auth:{session_id}"


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _redact_session(session: dict) -> dict:
    redacted = dict(session)
    if "qr_image_base64" in redacted:
        redacted["qr_image_base64"] = "<redacted>"
    return redacted
