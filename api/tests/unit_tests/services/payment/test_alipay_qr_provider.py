"""Unit tests for AlipayQrProvider (alipay.trade.precreate channel)."""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest

from services.payment.alipay_client import AlipayClient
from services.payment.alipay_qr_provider import AlipayQrProvider
from services.payment.exceptions import ProviderBusinessError
from services.payment.provider import PaymentProvider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> mock.MagicMock:
    """A MagicMock that mimics the AlipayClient surface used by the provider."""
    client = mock.MagicMock(spec=AlipayClient)
    return client


@pytest.fixture
def provider(mock_client: mock.MagicMock) -> AlipayQrProvider:
    return AlipayQrProvider(mock_client)


# ---------------------------------------------------------------------------
# create_order: happy path
# ---------------------------------------------------------------------------


def test_create_order_happy_path_returns_qr_code_and_raw(
    provider: AlipayQrProvider, mock_client: mock.MagicMock
) -> None:
    # Arrange
    upstream_response: dict[str, Any] = {
        "code": "10000",
        "msg": "Success",
        "out_trade_no": "TOPUP202604140001",
        "qr_code": "https://qr.alipay.com/bax00001abcd",
    }
    mock_client.request.return_value = upstream_response

    # Act
    result = provider.create_order(
        out_trade_no="TOPUP202604140001",
        amount_fen=1234,
        subject="Dify 钱包充值",
        timeout_express="15m",
    )

    # Assert
    assert result["qr_code"] == "https://qr.alipay.com/bax00001abcd"
    assert result["pay_url"] is None
    assert result["provider_trade_no"] is None
    assert json.loads(result["raw"]) == upstream_response

    mock_client.request.assert_called_once()
    method, biz_content = mock_client.request.call_args.args
    assert method == "alipay.trade.precreate"
    assert biz_content["out_trade_no"] == "TOPUP202604140001"
    assert biz_content["subject"] == "Dify 钱包充值"
    assert biz_content["product_code"] == "QR_CODE_OFFLINE"
    assert biz_content["timeout_express"] == "15m"


# ---------------------------------------------------------------------------
# create_order: business failure -> ProviderBusinessError
# ---------------------------------------------------------------------------


def test_create_order_business_failure_raises_provider_error(
    provider: AlipayQrProvider, mock_client: mock.MagicMock
) -> None:
    # Arrange
    mock_client.request.return_value = {
        "code": "40004",
        "msg": "Business Failed",
        "sub_code": "ACQ.TRADE_HAS_CLOSED",
        "sub_msg": "交易已关闭",
    }

    # Act / Assert
    with pytest.raises(ProviderBusinessError) as excinfo:
        provider.create_order(
            out_trade_no="TOPUP_CLOSED",
            amount_fen=100,
            subject="充值",
            timeout_express="15m",
        )

    err = excinfo.value
    assert err.code == "40004"
    assert err.sub_code == "ACQ.TRADE_HAS_CLOSED"
    assert err.sub_msg == "交易已关闭"
    # Human-readable message contains the upstream detail so ops can read logs.
    assert "ACQ.TRADE_HAS_CLOSED" in str(err)


# ---------------------------------------------------------------------------
# create_order: amount_fen precision conversions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount_fen", "expected_total_amount"),
    [
        (1234, "12.34"),
        (100, "1.00"),
        (1, "0.01"),
        (10000, "100.00"),
        (99999, "999.99"),
    ],
)
def test_create_order_converts_fen_to_two_decimal_yuan(
    provider: AlipayQrProvider,
    mock_client: mock.MagicMock,
    amount_fen: int,
    expected_total_amount: str,
) -> None:
    # Arrange
    mock_client.request.return_value = {
        "code": "10000",
        "qr_code": "https://qr.alipay.com/bax_amount_test",
    }

    # Act
    provider.create_order(
        out_trade_no="TOPUP_AMOUNT",
        amount_fen=amount_fen,
        subject="充值",
        timeout_express="15m",
    )

    # Assert
    _method, biz_content = mock_client.request.call_args.args
    assert biz_content["total_amount"] == expected_total_amount
    # total_amount MUST be a string per Alipay spec (price(12) type).
    assert isinstance(biz_content["total_amount"], str)


# ---------------------------------------------------------------------------
# create_order: client_ip propagation
# ---------------------------------------------------------------------------


def test_create_order_forwards_client_ip_in_business_params(
    provider: AlipayQrProvider, mock_client: mock.MagicMock
) -> None:
    # Arrange
    mock_client.request.return_value = {
        "code": "10000",
        "qr_code": "https://qr.alipay.com/bax_ip",
    }

    # Act
    provider.create_order(
        out_trade_no="TOPUP_IP",
        amount_fen=500,
        subject="充值",
        timeout_express="15m",
        client_ip="203.0.113.42",
    )

    # Assert
    _method, biz_content = mock_client.request.call_args.args
    # Alipay expects client IP inside business_params.mc_create_trade_ip.
    assert biz_content["business_params"]["mc_create_trade_ip"] == "203.0.113.42"


def test_create_order_omits_business_params_when_no_client_ip(
    provider: AlipayQrProvider, mock_client: mock.MagicMock
) -> None:
    # Arrange
    mock_client.request.return_value = {
        "code": "10000",
        "qr_code": "https://qr.alipay.com/bax_no_ip",
    }

    # Act
    provider.create_order(
        out_trade_no="TOPUP_NO_IP",
        amount_fen=500,
        subject="充值",
        timeout_express="15m",
    )

    # Assert
    _method, biz_content = mock_client.request.call_args.args
    assert "business_params" not in biz_content


# ---------------------------------------------------------------------------
# query_order
# ---------------------------------------------------------------------------


def test_query_order_invokes_trade_query_and_returns_response(
    provider: AlipayQrProvider, mock_client: mock.MagicMock
) -> None:
    # Arrange
    expected_response = {
        "code": "10000",
        "trade_status": "TRADE_SUCCESS",
        "out_trade_no": "TOPUP_Q",
    }
    mock_client.request.return_value = expected_response

    # Act
    result = provider.query_order("TOPUP_Q")

    # Assert
    mock_client.request.assert_called_once_with("alipay.trade.query", {"out_trade_no": "TOPUP_Q"})
    assert result == expected_response


# ---------------------------------------------------------------------------
# close_order
# ---------------------------------------------------------------------------


def test_close_order_invokes_trade_close_and_returns_response(
    provider: AlipayQrProvider, mock_client: mock.MagicMock
) -> None:
    # Arrange
    expected_response = {"code": "10000", "out_trade_no": "TOPUP_C"}
    mock_client.request.return_value = expected_response

    # Act
    result = provider.close_order("TOPUP_C")

    # Assert
    mock_client.request.assert_called_once_with("alipay.trade.close", {"out_trade_no": "TOPUP_C"})
    assert result == expected_response


# ---------------------------------------------------------------------------
# verify_notify: delegation to AlipayClient
# ---------------------------------------------------------------------------


def test_verify_notify_delegates_true(provider: AlipayQrProvider, mock_client: mock.MagicMock) -> None:
    # Arrange
    mock_client.verify_notify.return_value = True
    params = {"out_trade_no": "T", "trade_status": "TRADE_SUCCESS", "sign": "xxx"}

    # Act
    result = provider.verify_notify(params)

    # Assert
    assert result is True
    mock_client.verify_notify.assert_called_once_with(params)


def test_verify_notify_delegates_false(provider: AlipayQrProvider, mock_client: mock.MagicMock) -> None:
    # Arrange
    mock_client.verify_notify.return_value = False

    # Act
    result = provider.verify_notify({"sign": "tampered"})

    # Assert
    assert result is False


# ---------------------------------------------------------------------------
# Metadata / Protocol conformance
# ---------------------------------------------------------------------------


def test_provider_name_is_alipay_qr(mock_client: mock.MagicMock) -> None:
    # Arrange / Act
    provider = AlipayQrProvider(mock_client)

    # Assert
    assert provider.name == "alipay_qr"


def test_provider_satisfies_payment_provider_protocol(
    provider: AlipayQrProvider,
) -> None:
    # Act / Assert
    assert isinstance(provider, PaymentProvider)
