"""Unit tests for PaymentAlerter Protocol + concrete implementations.

The Protocol lets PaymentService inject any transport (log, email, Slack)
without structural coupling. These tests exercise the contract and the
two default implementations.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest

from models.creator import PaymentOrder, PaymentOrderStatus, PaymentProviderName
from services.payment.alerter import (
    LoggingPaymentAlerter,
    NullPaymentAlerter,
    PaymentAlerter,
)


def _make_order(
    *,
    out_trade_no: str = "TOPUP20260414ABCD1234",
    tenant_id: str = "tenant-abc",
    account_id: str = "account-xyz",
    amount_fen: int = 50_000,
    provider: str = PaymentProviderName.ALIPAY_QR.value,
) -> PaymentOrder:
    order = PaymentOrder(
        provider=provider,
        out_trade_no=out_trade_no,
        tenant_id=tenant_id,
        account_id=account_id,
        amount=Decimal(amount_fen) / Decimal(100),
        amount_fen=amount_fen,
        subject="test topup",
    )
    order.status = PaymentOrderStatus.PENDING.value
    return order


# ---------------------------------------------------------------------------
# LoggingPaymentAlerter
# ---------------------------------------------------------------------------


def test_logging_alerter_emits_warning_with_key_fields(caplog: pytest.LogCaptureFixture) -> None:
    # Arrange
    alerter = LoggingPaymentAlerter()
    order = _make_order(
        out_trade_no="TOPUP20260414DEADBEEF",
        tenant_id="tenant-abc",
        amount_fen=80_000,
    )

    # Act
    with caplog.at_level(logging.WARNING, logger="services.payment.alerter"):
        alerter.alert_large_amount(order, threshold_fen=5_000)

    # Assert
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)
    message = caplog.text
    assert "TOPUP20260414DEADBEEF" in message
    assert "amount_fen=80000" in message
    assert "threshold_fen=5000" in message
    assert "tenant-abc" in message


def test_logging_alerter_returns_none(caplog: pytest.LogCaptureFixture) -> None:
    alerter = LoggingPaymentAlerter()
    order = _make_order()

    result = alerter.alert_large_amount(order, threshold_fen=5_000)

    assert result is None


# ---------------------------------------------------------------------------
# NullPaymentAlerter
# ---------------------------------------------------------------------------


def test_null_alerter_does_not_raise_and_returns_none() -> None:
    alerter = NullPaymentAlerter()
    order = _make_order()

    # Should be a total no-op.
    assert alerter.alert_large_amount(order, threshold_fen=5_000) is None


def test_null_alerter_emits_nothing(caplog: pytest.LogCaptureFixture) -> None:
    alerter = NullPaymentAlerter()
    order = _make_order()

    with caplog.at_level(logging.DEBUG, logger="services.payment.alerter"):
        alerter.alert_large_amount(order, threshold_fen=5_000)

    assert caplog.records == []


# ---------------------------------------------------------------------------
# Protocol runtime structural check
# ---------------------------------------------------------------------------


def test_logging_alerter_satisfies_protocol() -> None:
    assert isinstance(LoggingPaymentAlerter(), PaymentAlerter)


def test_null_alerter_satisfies_protocol() -> None:
    assert isinstance(NullPaymentAlerter(), PaymentAlerter)
