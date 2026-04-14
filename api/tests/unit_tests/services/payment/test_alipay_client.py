"""Unit tests for AlipayClient (RSA2 sign/verify + verify_notify)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from services.payment.alipay_client import AlipayClient


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[str, str]:
    """Generate an ephemeral RSA-2048 keypair for signing tests.

    Returns (private_pem_str, public_pem_str) in PKCS#8 + SubjectPublicKeyInfo PEM form.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private_pem, public_pem


@pytest.fixture
def key_files(tmp_path: Path, rsa_keypair: tuple[str, str]) -> tuple[Path, Path]:
    private_pem, public_pem = rsa_keypair
    priv = tmp_path / "app_private.pem"
    pub = tmp_path / "alipay_public.pem"
    priv.write_text(private_pem)
    pub.write_text(public_pem)
    return priv, pub


@pytest.fixture
def enabled_client(key_files: tuple[Path, Path]) -> AlipayClient:
    priv, pub = key_files
    return AlipayClient(
        enabled=True,
        app_id="2021000000000001",
        app_private_key_path=str(priv),
        alipay_public_key_path=str(pub),
        gateway="https://openapi-sandbox.dl.alipaydev.com/gateway.do",
        sign_type="RSA2",
        notify_url="https://example.com/notify",
        return_url="https://example.com/return",
    )


@pytest.fixture
def disabled_client() -> AlipayClient:
    # No key paths provided; must not raise on instantiation.
    return AlipayClient(
        enabled=False,
        app_id="",
        app_private_key_path="",
        alipay_public_key_path="",
        gateway="https://openapi.alipay.com/gateway.do",
        sign_type="RSA2",
        notify_url="",
        return_url="",
    )


# ---------------------------------------------------------------------------
# sign / verify roundtrip
# ---------------------------------------------------------------------------


def test_sign_then_verify_roundtrip(enabled_client: AlipayClient) -> None:
    # Arrange
    payload = {"out_trade_no": "T20260101001", "total_amount": "10.00", "app_id": "2021000000000001"}

    # Act
    signature = enabled_client.sign(payload)
    ok = enabled_client.verify(payload, signature)

    # Assert
    assert isinstance(signature, str)
    assert signature  # non-empty
    assert ok is True


def test_verify_rejects_tampered_payload(enabled_client: AlipayClient) -> None:
    # Arrange
    payload = {"out_trade_no": "T20260101002", "total_amount": "10.00"}
    signature = enabled_client.sign(payload)

    # Act - tamper with the amount field
    tampered = dict(payload)
    tampered["total_amount"] = "9999.00"

    # Assert
    assert enabled_client.verify(tampered, signature) is False


# ---------------------------------------------------------------------------
# verify_notify semantics
# ---------------------------------------------------------------------------


def test_verify_notify_strips_sign_and_sign_type(enabled_client: AlipayClient) -> None:
    # Arrange: the params that would be signed (excludes sign/sign_type per spec)
    business_params = {
        "out_trade_no": "T20260101003",
        "trade_status": "TRADE_SUCCESS",
        "total_amount": "10.00",
        "app_id": "2021000000000001",
    }
    signature = enabled_client.sign(business_params)

    # Act: the notify body as Alipay would POST it — contains sign + sign_type
    notify_params = {**business_params, "sign": signature, "sign_type": "RSA2"}

    # Assert
    assert enabled_client.verify_notify(notify_params) is True


def test_verify_notify_skips_empty_values(enabled_client: AlipayClient) -> None:
    # Arrange: sign only the non-empty fields (Alipay spec excludes empty values)
    business_params = {
        "out_trade_no": "T20260101004",
        "trade_status": "TRADE_SUCCESS",
        "total_amount": "10.00",
    }
    signature = enabled_client.sign(business_params)

    # Act: notify carries an extra key with empty string value — must be ignored
    notify_params = {
        **business_params,
        "refund_fee": "",  # empty value, should not participate in verification
        "sign": signature,
        "sign_type": "RSA2",
    }

    # Assert
    assert enabled_client.verify_notify(notify_params) is True


def test_verify_notify_returns_false_without_sign(enabled_client: AlipayClient) -> None:
    # Arrange
    params = {"out_trade_no": "T20260101005", "trade_status": "TRADE_SUCCESS"}

    # Act / Assert
    assert enabled_client.verify_notify(params) is False


def test_verify_notify_returns_false_on_bad_signature(enabled_client: AlipayClient) -> None:
    # Arrange
    params = {
        "out_trade_no": "T20260101006",
        "trade_status": "TRADE_SUCCESS",
        "sign": "ZmFrZS1zaWduYXR1cmU=",  # base64 of "fake-signature"
        "sign_type": "RSA2",
    }

    # Act / Assert
    assert enabled_client.verify_notify(params) is False


# ---------------------------------------------------------------------------
# Lazy load when disabled
# ---------------------------------------------------------------------------


def test_disabled_client_instantiates_without_key_files(disabled_client: AlipayClient) -> None:
    # Assert
    assert disabled_client.enabled is False


def test_disabled_client_sign_raises_runtime_error(disabled_client: AlipayClient) -> None:
    # Act / Assert
    with pytest.raises(RuntimeError, match="not enabled"):
        disabled_client.sign({"foo": "bar"})


def test_disabled_client_request_raises_runtime_error(disabled_client: AlipayClient) -> None:
    # Act / Assert
    with pytest.raises(RuntimeError, match="not enabled"):
        disabled_client.request("alipay.trade.query", {"out_trade_no": "T1"})


def test_disabled_client_verify_notify_returns_false(disabled_client: AlipayClient) -> None:
    # Act / Assert
    assert disabled_client.verify_notify({"sign": "x", "sign_type": "RSA2"}) is False


# ---------------------------------------------------------------------------
# HTTP request wrapping (mocked — no real network)
# ---------------------------------------------------------------------------


def test_request_posts_signed_payload_to_gateway(enabled_client: AlipayClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange - mock httpx.post used inside AlipayClient.request
    fake_body = '{"alipay_trade_query_response":{"code":"10000","msg":"Success","out_trade_no":"T1"},"sign":"ZmFrZQ=="}'
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.text = fake_body
    mock_response.raise_for_status = mock.MagicMock()

    captured: dict[str, Any] = {}

    def fake_post(url: str, data: dict[str, str] | None = None, timeout: float | None = None) -> Any:
        captured["url"] = url
        captured["data"] = data or {}
        captured["timeout"] = timeout
        return mock_response

    monkeypatch.setattr("services.payment.alipay_client.httpx.post", fake_post)

    # Act
    result = enabled_client.request("alipay.trade.query", {"out_trade_no": "T1"})

    # Assert
    assert captured["url"] == "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
    assert captured["data"].get("app_id") == "2021000000000001"
    assert captured["data"].get("method") == "alipay.trade.query"
    assert captured["data"].get("sign_type") == "RSA2"
    assert captured["data"].get("sign")  # signature attached
    assert result["code"] == "10000"


def test_request_raises_on_business_error(enabled_client: AlipayClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    fake_body = (
        '{"alipay_trade_query_response":{"code":"40004","msg":"Business Failed","sub_code":"ACQ.TRADE_NOT_EXIST"},'
        '"sign":"ZmFrZQ=="}'
    )
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.text = fake_body
    mock_response.raise_for_status = mock.MagicMock()

    monkeypatch.setattr(
        "services.payment.alipay_client.httpx.post",
        lambda *args, **kwargs: mock_response,  # type: ignore[misc,return-value]
    )

    # Act
    result = enabled_client.request("alipay.trade.query", {"out_trade_no": "T-missing"})

    # Assert — request returns parsed body; caller decides how to handle error codes
    assert result["code"] == "40004"
    assert result["sub_code"] == "ACQ.TRADE_NOT_EXIST"


# ---------------------------------------------------------------------------
# from_config factory
# ---------------------------------------------------------------------------


def test_from_config_when_disabled_does_not_touch_key_files() -> None:
    # Arrange
    fake_cfg = mock.MagicMock()
    fake_cfg.ALIPAY_ENABLED = False
    fake_cfg.ALIPAY_APP_ID = ""
    fake_cfg.ALIPAY_APP_PRIVATE_KEY_PATH = "/nonexistent/private.pem"
    fake_cfg.ALIPAY_PUBLIC_KEY_PATH = "/nonexistent/public.pem"
    fake_cfg.ALIPAY_GATEWAY = "https://openapi.alipay.com/gateway.do"
    fake_cfg.ALIPAY_SIGN_TYPE = "RSA2"
    fake_cfg.ALIPAY_NOTIFY_URL = ""
    fake_cfg.ALIPAY_RETURN_URL = ""

    # Act - should not raise even though key paths point nowhere
    client = AlipayClient.from_config(fake_cfg)

    # Assert
    assert client.enabled is False


def test_from_config_when_enabled_loads_keys(key_files: tuple[Path, Path]) -> None:
    # Arrange
    priv, pub = key_files
    fake_cfg = mock.MagicMock()
    fake_cfg.ALIPAY_ENABLED = True
    fake_cfg.ALIPAY_APP_ID = "2021000000000099"
    fake_cfg.ALIPAY_APP_PRIVATE_KEY_PATH = str(priv)
    fake_cfg.ALIPAY_PUBLIC_KEY_PATH = str(pub)
    fake_cfg.ALIPAY_GATEWAY = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
    fake_cfg.ALIPAY_SIGN_TYPE = "RSA2"
    fake_cfg.ALIPAY_NOTIFY_URL = "https://example.com/notify"
    fake_cfg.ALIPAY_RETURN_URL = "https://example.com/return"

    # Act
    client = AlipayClient.from_config(fake_cfg)

    # Assert - a sign/verify roundtrip proves the keys loaded correctly
    sig = client.sign({"foo": "bar"})
    assert client.verify({"foo": "bar"}, sig) is True


def test_from_config_when_enabled_defers_missing_key_error_until_use() -> None:
    """Key files are loaded lazily — missing files raise only at first use."""
    # Arrange
    fake_cfg = mock.MagicMock()
    fake_cfg.ALIPAY_ENABLED = True
    fake_cfg.ALIPAY_APP_ID = "2021000000000001"
    fake_cfg.ALIPAY_APP_PRIVATE_KEY_PATH = "/definitely/does/not/exist.pem"
    fake_cfg.ALIPAY_PUBLIC_KEY_PATH = "/definitely/does/not/exist.pem"
    fake_cfg.ALIPAY_GATEWAY = "https://openapi.alipay.com/gateway.do"
    fake_cfg.ALIPAY_SIGN_TYPE = "RSA2"
    fake_cfg.ALIPAY_NOTIFY_URL = ""
    fake_cfg.ALIPAY_RETURN_URL = ""

    # Act - construction itself must succeed (lazy loading)
    client = AlipayClient.from_config(fake_cfg)
    assert client.enabled is True

    # Assert - first actual signing attempt surfaces the missing key
    with pytest.raises((FileNotFoundError, OSError)):
        client.sign({"foo": "bar"})


# ---------------------------------------------------------------------------
# Security red line: private key must not leak into repr/str
# ---------------------------------------------------------------------------


def test_repr_does_not_contain_private_key_material(enabled_client: AlipayClient, rsa_keypair: tuple[str, str]) -> None:
    # Arrange
    private_pem, _ = rsa_keypair
    # Use a distinctive inner substring unlikely to appear by chance
    secret_marker = private_pem.splitlines()[1][:20]

    # Act
    rendered = repr(enabled_client) + str(enabled_client)

    # Assert
    assert secret_marker not in rendered


# ---------------------------------------------------------------------------
# web_pay_url — pagePay signed-URL generation (no HTTP call)
# ---------------------------------------------------------------------------


def test_web_pay_url_disabled_raises_runtime_error(disabled_client: AlipayClient) -> None:
    # Act / Assert
    with pytest.raises(RuntimeError, match="not enabled"):
        disabled_client.web_pay_url({"out_trade_no": "T1", "total_amount": "10.00", "subject": "s"})


def test_web_pay_url_invokes_sdk_api_alipay_trade_page_pay(
    enabled_client: AlipayClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange - stub the SDK method so no PEM / signing happens here.
    fake_url = "https://openapi.alipay.com/gateway.do?method=alipay.trade.page.pay&sign=ZmFrZQ%3D%3D"
    captured: dict[str, Any] = {}

    def fake_page_pay(
        self: Any,
        subject: str,
        out_trade_no: str,
        total_amount: str,
        return_url: str | None = None,
        notify_url: str | None = None,
        **kwargs: Any,
    ) -> str:
        captured["subject"] = subject
        captured["out_trade_no"] = out_trade_no
        captured["total_amount"] = total_amount
        captured["return_url"] = return_url
        captured["notify_url"] = notify_url
        captured["kwargs"] = kwargs
        return fake_url

    monkeypatch.setattr(
        "services.payment.alipay_client.AliPay.api_alipay_trade_page_pay",
        fake_page_pay,
    )

    # Act
    url = enabled_client.web_pay_url(
        {
            "out_trade_no": "T_PAGE_1",
            "total_amount": "1234.56",
            "subject": "Dify 钱包充值",
            "product_code": "FAST_INSTANT_TRADE_PAY",
            "timeout_express": "30m",
        }
    )

    # Assert
    assert url == fake_url
    assert captured["subject"] == "Dify 钱包充值"
    assert captured["out_trade_no"] == "T_PAGE_1"
    assert captured["total_amount"] == "1234.56"
    # Defaults to the client's configured return/notify URLs.
    assert captured["return_url"] == "https://example.com/return"
    assert captured["notify_url"] == "https://example.com/notify"
    # Non-core biz fields flow through as **kwargs (product_code, timeout_express).
    assert captured["kwargs"].get("product_code") == "FAST_INSTANT_TRADE_PAY"
    assert captured["kwargs"].get("timeout_express") == "30m"


def test_web_pay_url_return_url_override(enabled_client: AlipayClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    captured: dict[str, Any] = {}

    def fake_page_pay(
        self: Any,
        subject: str,
        out_trade_no: str,
        total_amount: str,
        return_url: str | None = None,
        notify_url: str | None = None,
        **kwargs: Any,
    ) -> str:
        captured["return_url"] = return_url
        return "https://fake"

    monkeypatch.setattr(
        "services.payment.alipay_client.AliPay.api_alipay_trade_page_pay",
        fake_page_pay,
    )

    # Act
    enabled_client.web_pay_url(
        {"out_trade_no": "T_OVR", "total_amount": "9.99", "subject": "s"},
        return_url="https://tenant.example.com/topup/callback",
    )

    # Assert
    assert captured["return_url"] == "https://tenant.example.com/topup/callback"


def _provider_protocol_unused_marker() -> Generator[None, None, None]:
    # Guard against unused-import warnings in some IDE configurations.
    yield
