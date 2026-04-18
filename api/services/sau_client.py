"""HTTP client for the sau (social-auto-upload) service.

A single pooled `httpx.Client` is reused across the process. All requests are
authenticated with the shared `X-Sau-Token` header. Network/timeout errors and
5xx responses are retried with exponential backoff; 4xx responses fail fast.

This module is the only place that knows about sau's wire protocol — the rest
of the codebase consumes the typed DTOs returned here.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from configs import dify_config
from core.helper.http_client_pooling import get_pooled_http_client
from services.errors.social_publish import SauApiError, SauUnreachableError

logger = logging.getLogger(__name__)

# Catch the broader transient categories so pool/connect timeouts and other
# subclasses don't escape as raw httpx exceptions and surface as 500s.
# `httpx.RequestError` is the umbrella for ConnectError, all TimeoutException
# subclasses (ConnectTimeout / ReadTimeout / WriteTimeout / PoolTimeout),
# RemoteProtocolError, and NetworkError variants.
_RETRYABLE_NETWORK_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)

Platform = Literal["douyin", "xhs", "ks"]


# ---------- DTOs ----------


@dataclass(frozen=True)
class SauLoginInitResponse:
    qr_image_base64: str
    expires_in: int


@dataclass(frozen=True)
class SauLoginProfile:
    display_name: str | None
    avatar_url: str | None


@dataclass(frozen=True)
class SauLoginStatusResponse:
    status: Literal["waiting", "scanned", "success", "expired", "failed"]
    sau_account_id: str | None
    profile: SauLoginProfile | None
    message: str | None = None


@dataclass(frozen=True)
class SauCheckResponse:
    valid: bool
    reason: str | None


# ---------- Client ----------


class SauClient:
    """Synchronous HTTP client for sau."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float,
        max_retries: int,
        pool_size: int,
        retry_backoff_seconds: float = 0.2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token or len(token) < 16:
            raise RuntimeError("SAU_INTERNAL_TOKEN must be set and >= 16 chars")
        self._base_url = base_url.rstrip("/")
        self._max_retries = max(0, int(max_retries))
        self._retry_backoff_seconds = retry_backoff_seconds
        # ``transport`` is a unit-test seam: pass an httpx.MockTransport from
        # tests to assert wire-level behaviour without going through the
        # global pool.
        if transport is not None:
            self._client = httpx.Client(
                transport=transport,
                timeout=httpx.Timeout(timeout_seconds),
                headers={
                    "X-Sau-Token": token,
                    "User-Agent": "dify-api/sau-client",
                },
            )
        else:
            self._client = get_pooled_http_client(
                "sau:default",
                lambda: httpx.Client(
                    timeout=httpx.Timeout(timeout_seconds),
                    limits=httpx.Limits(
                        max_connections=pool_size,
                        max_keepalive_connections=pool_size,
                    ),
                    headers={
                        "X-Sau-Token": token,
                        "User-Agent": "dify-api/sau-client",
                    },
                ),
            )

    # -------- public API --------

    def start_login(
        self,
        *,
        tenant_id: str,
        platform: Platform,
        session_id: str,
        sau_account_id: str | None = None,
    ) -> SauLoginInitResponse:
        body = {
            "tenant_id": tenant_id,
            "platform": platform,
            "session_id": session_id,
        }
        if sau_account_id is not None:
            body["sau_account_id"] = sau_account_id
        data = self._request("POST", "/login", json=body)
        return SauLoginInitResponse(
            qr_image_base64=str(data["qr_image_base64"]),
            expires_in=int(data.get("expires_in", 180)),
        )

    def get_login_status(self, *, session_id: str) -> SauLoginStatusResponse:
        data = self._request("GET", f"/login/status/{session_id}")
        profile_payload = data.get("profile")
        profile = (
            SauLoginProfile(
                display_name=profile_payload.get("display_name"),
                avatar_url=profile_payload.get("avatar_url"),
            )
            if isinstance(profile_payload, dict)
            else None
        )
        return SauLoginStatusResponse(
            status=data["status"],
            sau_account_id=data.get("sau_account_id"),
            profile=profile,
            message=data.get("message"),
        )

    def check_account(
        self,
        *,
        tenant_id: str,
        platform: Platform,
        sau_account_id: str,
    ) -> SauCheckResponse:
        data = self._request(
            "GET",
            f"/accounts/{sau_account_id}/check",
            params={"tenant_id": tenant_id, "platform": platform},
        )
        return SauCheckResponse(
            valid=bool(data.get("valid", False)),
            reason=data.get("reason"),
        )

    def delete_account(
        self,
        *,
        tenant_id: str,
        platform: Platform,
        sau_account_id: str,
    ) -> None:
        self._request(
            "POST",
            f"/accounts/{sau_account_id}/delete",
            params={"tenant_id": tenant_id, "platform": platform},
        )

    # -------- internals --------

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.request(method, url, **kwargs)
            except _RETRYABLE_NETWORK_ERRORS as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    logger.warning("sau request failed after %d attempts: %s", attempt + 1, exc)
                    raise SauUnreachableError(str(exc)) from exc
                self._sleep_backoff(attempt)
                continue

            if 500 <= resp.status_code < 600 and attempt < self._max_retries:
                logger.info("sau %s %s -> %d, retrying", method, path, resp.status_code)
                self._sleep_backoff(attempt)
                continue

            if resp.status_code >= 400:
                raise SauApiError(resp.status_code, resp.text)

            try:
                return resp.json()
            except ValueError as exc:
                raise SauApiError(resp.status_code, "invalid json") from exc

        # unreachable: loop above either returns or raises
        raise SauUnreachableError(str(last_exc) if last_exc else "unknown")

    def _sleep_backoff(self, attempt: int) -> None:
        time.sleep(self._retry_backoff_seconds * (2**attempt))


# ---------- module-level singleton ----------

_singleton: SauClient | None = None


def get_sau_client() -> SauClient:
    """Return the process-wide SauClient.

    The client is constructed lazily so test suites and CLI commands that don't
    touch the publish-center don't pay the cost.

    **Restart-required semantics**: SAU base URL, token, timeout, retries and
    pool size are read once and frozen for the process lifetime. Because the
    underlying ``httpx.Client`` is also pooled under the fixed key
    ``"sau:default"``, changing those env vars (or ``SAU_INTERNAL_TOKEN``)
    requires a process restart. ``reset_sau_client_for_tests`` is the only
    sanctioned reinit path and is intended for unit tests only.
    """
    global _singleton
    if _singleton is not None:
        return _singleton

    token = dify_config.SAU_INTERNAL_TOKEN
    if not token:
        raise RuntimeError(
            "SAU_INTERNAL_TOKEN is not configured; set it in api/.env or "
            "disable SOCIAL_PUBLISH_ENABLED."
        )

    _singleton = SauClient(
        base_url=dify_config.SAU_BASE_URL,
        token=token,
        timeout_seconds=dify_config.SAU_HTTP_TIMEOUT_SECONDS,
        max_retries=dify_config.SAU_HTTP_MAX_RETRIES,
        pool_size=dify_config.SAU_HTTP_POOL_SIZE,
    )
    return _singleton


def reset_sau_client_for_tests() -> None:
    """Test helper — clear the cached singleton between unit tests."""
    global _singleton
    _singleton = None
