"""Unit tests for AlipayPageProvider (alipay.trade.page.pay channel)."""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest

from services.payment.alipay_client import AlipayClient
from services.payment.alipay_page_provider import AlipayPageProvider
from services.payment.provider import PaymentProvider

_FAKE_PAY_URL = (
    "https://openapi.alipay.com/gateway.do?"
    "app_id=2021000000000001&charset=utf-8&method=alipay.trade.page.pay"
    "&biz_content=%7B%22out_trade_no%22%3A%22T1%22%7D&sign_type=RSA2&sign=ZmFrZQ%3D%3D"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> mock.MagicMock:
    """A MagicMock mirroring the subset of AlipayClient the provider calls."""
    client = mock.MagicMock(spec=AlipayClient)
    client.web_pay_url.return_value = _FAKE_PAY_URL
    return client


@pytest.fixture
def provider(mock_client: mock.MagicMock) -> AlipayPageProvider:
    return AlipayPageProvider(mock_client)


# ---------------------------------------------------------------------------
# create_order: happy path
# ---------------------------------------------------------------------------


def test_create_order_happy_path_returns_pay_url(provider: AlipayPageProvider, mock_client: mock.MagicMock) -> None:
    # Act
    result = provider.create_order(
        out_trade_no="TOPUP202604140001",
        amount_fen=123_400,  # ¥1234.00
        subject="Dify 钱包充值",
        timeout_express="30m",
    )

    # Assert
    assert result["pay_url"] == _FAKE_PAY_URL
    assert result["qr_code"] is None
    assert result["provider_trade_no"] is None
    # raw is a JSON string; persisted on PaymentOrder.prepay_raw for audit.
    raw_payload: dict[str, Any] = json.loads(result["raw"])
    assert raw_payload == {"pay_url": _FAKE_PAY_URL}


def test_create_order_passes_correct_biz_content_to_client(
    provider: AlipayPageProvider, mock_client: mock.MagicMock
) -> None:
    # Act
    provider.create_order(
        out_trade_no="TOPUP_A",
        amount_fen=50_000,  # ¥500.00
        subject="充值 500",
        timeout_express="30m",
    )

    # Assert
    mock_client.web_pay_url.assert_called_once()
    (biz_content,) = mock_client.web_pay_url.call_args.args
    assert biz_content["out_trade_no"] == "TOPUP_A"
    assert biz_content["subject"] == "充值 500"
    assert biz_content["total_amount"] == "500.00"
    assert biz_content["product_code"] == "FAST_INSTANT_TRADE_PAY"
    assert biz_content["timeout_express"] == "30m"


# ---------------------------------------------------------------------------
# create_order: amount precision (shared _amount helper)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount_fen", "expected_total_amount"),
    [
        (1, "0.01"),
        (100, "1.00"),
        (1234, "12.34"),
        (10_000_000, "100000.00"),
        (99_999_999, "999999.99"),
    ],
)
def test_create_order_converts_fen_to_two_decimal_yuan(
    provider: AlipayPageProvider,
    mock_client: mock.MagicMock,
    amount_fen: int,
    expected_total_amount: str,
) -> None:
    # Act
    provider.create_order(
        out_trade_no="TOPUP_AMOUNT",
        amount_fen=amount_fen,
        subject="充值",
        timeout_express="30m",
    )

    # Assert
    (biz_content,) = mock_client.web_pay_url.call_args.args
    assert biz_content["total_amount"] == expected_total_amount
    assert isinstance(biz_content["total_amount"], str)


# ---------------------------------------------------------------------------
# create_order: client_ip propagation
# ---------------------------------------------------------------------------


def test_create_order_forwards_client_ip_in_business_params(
    provider: AlipayPageProvider, mock_client: mock.MagicMock
) -> None:
    # Act
    provider.create_order(
        out_trade_no="TOPUP_IP",
        amount_fen=100_000,
        subject="充值",
        timeout_express="30m",
        client_ip="203.0.113.42",
    )

    # Assert
    (biz_content,) = mock_client.web_pay_url.call_args.args
    assert biz_content["business_params"]["mc_create_trade_ip"] == "203.0.113.42"


def test_create_order_omits_business_params_when_no_client_ip(
    provider: AlipayPageProvider, mock_client: mock.MagicMock
) -> None:
    # Act
    provider.create_order(
        out_trade_no="TOPUP_NO_IP",
        amount_fen=100_000,
        subject="充值",
        timeout_express="30m",
    )

    # Assert
    (biz_content,) = mock_client.web_pay_url.call_args.args
    assert "business_params" not in biz_content


# ---------------------------------------------------------------------------
# query_order / close_order
# ---------------------------------------------------------------------------


def test_query_order_invokes_trade_query_and_returns_response(
    provider: AlipayPageProvider, mock_client: mock.MagicMock
) -> None:
    # Arrange
    expected = {"code": "10000", "trade_status": "TRADE_SUCCESS", "out_trade_no": "PAGE_Q"}
    mock_client.request.return_value = expected

    # Act
    result = provider.query_order("PAGE_Q")

    # Assert
    mock_client.request.assert_called_once_with("alipay.trade.query", {"out_trade_no": "PAGE_Q"})
    assert result == expected


def test_close_order_invokes_trade_close_and_returns_response(
    provider: AlipayPageProvider, mock_client: mock.MagicMock
) -> None:
    # Arrange
    expected = {"code": "10000", "out_trade_no": "PAGE_C"}
    mock_client.request.return_value = expected

    # Act
    result = provider.close_order("PAGE_C")

    # Assert
    mock_client.request.assert_called_once_with("alipay.trade.close", {"out_trade_no": "PAGE_C"})
    assert result == expected


# ---------------------------------------------------------------------------
# verify_notify: delegation
# ---------------------------------------------------------------------------


def test_verify_notify_delegates_true(provider: AlipayPageProvider, mock_client: mock.MagicMock) -> None:
    # Arrange
    mock_client.verify_notify.return_value = True
    params = {"out_trade_no": "T", "trade_status": "TRADE_SUCCESS", "sign": "xxx"}

    # Act
    result = provider.verify_notify(params)

    # Assert
    assert result is True
    mock_client.verify_notify.assert_called_once_with(params)


def test_verify_notify_delegates_false(provider: AlipayPageProvider, mock_client: mock.MagicMock) -> None:
    # Arrange
    mock_client.verify_notify.return_value = False

    # Act
    result = provider.verify_notify({"sign": "tampered"})

    # Assert
    assert result is False


# ---------------------------------------------------------------------------
# Metadata / Protocol conformance
# ---------------------------------------------------------------------------


def test_provider_name_is_alipay_page(mock_client: mock.MagicMock) -> None:
    # Arrange / Act
    p = AlipayPageProvider(mock_client)

    # Assert
    assert p.name == "alipay_page"


def test_provider_satisfies_payment_provider_protocol(
    provider: AlipayPageProvider,
) -> None:
    # Act / Assert
    assert isinstance(provider, PaymentProvider)
