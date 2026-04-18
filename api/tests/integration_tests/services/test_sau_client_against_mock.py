"""End-to-end smoke test for SauClient against the sau-mock service.

Skipped automatically when ``SAU_MOCK_E2E_URL`` is not set, so this file is
no-op in normal CI. To run locally:

    1. Start the mock (in social-auto-upload checkout):
         export SAU_INTERNAL_TOKEN=$(openssl rand -hex 32)
         uv run python scripts/sau_mock.py --port 8001
    2. From the dify api/ directory:
         export SAU_MOCK_E2E_URL=http://127.0.0.1:8001
         export SAU_INTERNAL_TOKEN=<same token>
         uv run pytest tests/integration_tests/services/test_sau_client_against_mock.py -v

Tunables on the mock side:
    MOCK_SCAN_DELAY_SEC=1
    MOCK_AUTH_DELAY_SEC=1

The test waits up to ~12 seconds for the scan-to-success transition.
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

from services.errors.social_publish import SauUnreachableError
from services.sau_client import (
    SauCheckResponse,
    SauClient,
    SauLoginInitResponse,
    SauLoginStatusResponse,
)

E2E_URL = os.getenv("SAU_MOCK_E2E_URL")
TOKEN = os.getenv("SAU_INTERNAL_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not E2E_URL or len(TOKEN) < 16,
    reason="set SAU_MOCK_E2E_URL + SAU_INTERNAL_TOKEN to run e2e against sau-mock",
)


@pytest.fixture
def client() -> SauClient:
    assert E2E_URL is not None
    return SauClient(
        base_url=E2E_URL,
        token=TOKEN,
        timeout_seconds=5.0,
        max_retries=1,
        pool_size=4,
        retry_backoff_seconds=0.1,
    )


def _wait_for_status(
    client: SauClient,
    session_id: str,
    target: str,
    timeout_s: float = 12.0,
) -> SauLoginStatusResponse:
    deadline = time.monotonic() + timeout_s
    last: SauLoginStatusResponse | None = None
    while time.monotonic() < deadline:
        last = client.get_login_status(session_id=session_id)
        if last.status == target:
            return last
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for status={target!r}; last={last!r}")


class TestEndToEndAgainstMock:
    def test_scan_to_success_then_check_then_delete(self, client):
        session_id = str(uuid.uuid4())
        tenant_id = "e2e-tenant"

        # 1. start_login -> qr image
        init = client.start_login(tenant_id=tenant_id, platform="douyin", session_id=session_id)
        assert isinstance(init, SauLoginInitResponse)
        assert init.qr_image_base64.startswith("data:image/png;base64,")

        # 2. poll until success (mock auto-progresses)
        final = _wait_for_status(client, session_id, "success")
        assert final.sau_account_id is not None
        assert final.profile is not None
        assert final.profile.display_name

        sau_account_id = final.sau_account_id

        # 3. check should report valid now
        check = client.check_account(
            tenant_id=tenant_id, platform="douyin", sau_account_id=sau_account_id
        )
        assert isinstance(check, SauCheckResponse)
        assert check.valid is True

        # 4. delete then re-check -> invalid
        client.delete_account(
            tenant_id=tenant_id, platform="douyin", sau_account_id=sau_account_id
        )
        recheck = client.check_account(
            tenant_id=tenant_id, platform="douyin", sau_account_id=sau_account_id
        )
        assert recheck.valid is False

    def test_unreachable_url_surfaces_as_sau_unreachable(self):
        # Use a TEST-NET-1 address (RFC 5737, never routable) to force a
        # connection-level failure and assert the transport-error mapping.
        bad_client = SauClient(
            base_url="http://192.0.2.1:9",
            token=TOKEN,
            timeout_seconds=1.0,
            max_retries=0,
            pool_size=1,
            retry_backoff_seconds=0.0,
        )
        with pytest.raises(SauUnreachableError):
            bad_client.check_account(
                tenant_id="e2e", platform="douyin", sau_account_id="missing"
            )
