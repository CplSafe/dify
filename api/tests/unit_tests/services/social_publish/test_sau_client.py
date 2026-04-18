"""Wire-level tests for SauClient.

These tests use ``httpx.MockTransport`` to assert that:
- the X-Sau-Token header is injected on every request,
- network errors / 5xx responses are retried with backoff,
- 4xx responses fail fast as ``SauApiError``,
- timeouts surface as ``SauUnreachableError``.

The retry backoff is set to ~0 so the suite stays fast.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from services.errors.social_publish import SauApiError, SauUnreachableError
from services.sau_client import (
    SauCheckResponse,
    SauClient,
    SauLoginInitResponse,
    SauLoginStatusResponse,
)

VALID_TOKEN = "x" * 32


def _build(handler: Callable[[httpx.Request], httpx.Response], **overrides: Any) -> SauClient:
    return SauClient(
        base_url="http://sau-api:8001",
        token=VALID_TOKEN,
        timeout_seconds=overrides.pop("timeout_seconds", 1.0),
        max_retries=overrides.pop("max_retries", 2),
        pool_size=overrides.pop("pool_size", 4),
        retry_backoff_seconds=overrides.pop("retry_backoff_seconds", 0.0),
        transport=httpx.MockTransport(handler),
    )


class TestTokenInjection:
    def test_x_sau_token_header_on_every_request(self):
        seen_tokens: list[str | None] = []

        def handler(req: httpx.Request) -> httpx.Response:
            seen_tokens.append(req.headers.get("X-Sau-Token"))
            return httpx.Response(200, json={"valid": True, "reason": "cookie_present"})

        client = _build(handler)
        client.check_account(tenant_id="t1", platform="douyin", sau_account_id="a1")
        client.check_account(tenant_id="t1", platform="douyin", sau_account_id="a2")

        assert seen_tokens == [VALID_TOKEN, VALID_TOKEN]


class TestRetryBehaviour:
    def test_retries_on_5xx_then_succeeds(self):
        calls: list[int] = []

        def handler(req: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) < 2:
                return httpx.Response(503, text="upstream busy")
            return httpx.Response(200, json={"valid": True, "reason": "cookie_present"})

        client = _build(handler, max_retries=2)
        result = client.check_account(tenant_id="t1", platform="douyin", sau_account_id="a1")

        assert isinstance(result, SauCheckResponse)
        assert result.valid is True
        assert len(calls) == 2

    def test_does_not_retry_on_4xx(self):
        calls: list[int] = []

        def handler(req: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(404, text="not found")

        client = _build(handler, max_retries=3)
        with pytest.raises(SauApiError) as exc_info:
            client.check_account(tenant_id="t1", platform="douyin", sau_account_id="missing")

        assert exc_info.value.status_code == 404
        assert len(calls) == 1

    def test_raises_unreachable_after_max_retries_on_network_error(self):
        calls: list[int] = []

        def handler(req: httpx.Request) -> httpx.Response:
            calls.append(1)
            raise httpx.ConnectError("nope")

        client = _build(handler, max_retries=2)
        with pytest.raises(SauUnreachableError):
            client.check_account(tenant_id="t1", platform="douyin", sau_account_id="a1")

        # 1 initial + 2 retries
        assert len(calls) == 3

    def test_timeout_propagates_as_unreachable(self):
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out")

        client = _build(handler, max_retries=1)
        with pytest.raises(SauUnreachableError):
            client.check_account(tenant_id="t1", platform="douyin", sau_account_id="a1")


class TestPublicApiShape:
    def test_start_login_returns_typed_dto(self):
        captured: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            captured["body"] = req.content.decode("utf-8")
            return httpx.Response(
                200,
                json={"qr_image_base64": "data:image/png;base64,FAKE", "expires_in": 120},
            )

        client = _build(handler)
        result = client.start_login(
            tenant_id="t1",
            platform="douyin",
            session_id="s1",
            sau_account_id="acc-1",
        )

        assert isinstance(result, SauLoginInitResponse)
        assert result.qr_image_base64.startswith("data:image/png;base64,")
        assert result.expires_in == 120
        assert "/login" in captured["url"]
        assert '"sau_account_id"' in captured["body"]

    def test_get_login_status_parses_profile(self):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "sau_account_id": "acc-1",
                    "profile": {"display_name": "小妹", "avatar_url": "https://x"},
                    "message": None,
                },
            )

        client = _build(handler)
        result = client.get_login_status(session_id="s1")

        assert isinstance(result, SauLoginStatusResponse)
        assert result.status == "success"
        assert result.profile is not None
        assert result.profile.display_name == "小妹"
        assert result.profile.avatar_url == "https://x"

    def test_invalid_json_body_surfaces_as_api_error(self):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>oops</html>")

        client = _build(handler)
        with pytest.raises(SauApiError):
            client.get_login_status(session_id="s1")


class TestConstructorValidation:
    def test_rejects_short_token(self):
        with pytest.raises(RuntimeError, match="SAU_INTERNAL_TOKEN"):
            SauClient(
                base_url="http://x",
                token="short",
                timeout_seconds=1.0,
                max_retries=0,
                pool_size=1,
            )
