"""Unit tests for the expired payment order cleanup task.

The task composes two collaborators (DB session + PaymentService), so these
tests mock both and focus on: (1) empty-result short-circuit, (2) happy-path
iteration count, (3) per-order exception handling, (4) parameter passing.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

import pytest

from models.creator import PaymentOrder, PaymentOrderStatus, PaymentProviderName
from services.payment.exceptions import (
    OrderAlreadyClosed,
    OrderNotFound,
    ProviderBusinessError,
)
from tasks.payment_order_expiry_tasks import close_expired_payment_orders


def _make_expired_order(
    *,
    out_trade_no: str,
    tenant_id: str = "t-1",
) -> PaymentOrder:
    order = PaymentOrder(
        provider=PaymentProviderName.ALIPAY_QR.value,
        out_trade_no=out_trade_no,
        tenant_id=tenant_id,
        account_id="a-1",
        amount=Decimal("5.00"),
        amount_fen=500,
        subject="test",
    )
    order.status = PaymentOrderStatus.PENDING.value
    return order


@pytest.fixture
def fake_service() -> mock.MagicMock:
    return mock.MagicMock()


@pytest.fixture
def patched_from_config(fake_service: mock.MagicMock):
    with mock.patch(
        "tasks.payment_order_expiry_tasks.PaymentService.from_config",
        return_value=fake_service,
    ) as patched:
        yield patched


@pytest.fixture
def patched_db():
    with mock.patch("tasks.payment_order_expiry_tasks.db") as patched:
        yield patched


def _stub_scalars(mock_db: mock.MagicMock, rows: list[PaymentOrder]) -> None:
    scalars_result = mock.MagicMock()
    scalars_result.all.return_value = rows
    mock_db.session.scalars.return_value = scalars_result


# ---------------------------------------------------------------------------
# No expired orders — short-circuit
# ---------------------------------------------------------------------------


def test_returns_zero_when_no_expired_orders(
    patched_db: mock.MagicMock,
    patched_from_config: mock.MagicMock,
    fake_service: mock.MagicMock,
) -> None:
    # Arrange
    _stub_scalars(patched_db, [])

    # Act
    result = close_expired_payment_orders()

    # Assert
    assert result == 0
    # Nothing to do → close_order never invoked.
    fake_service.close_order.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path — two orders, both close cleanly
# ---------------------------------------------------------------------------


def test_closes_all_expired_orders_returns_count(
    patched_db: mock.MagicMock,
    patched_from_config: mock.MagicMock,
    fake_service: mock.MagicMock,
) -> None:
    orders = [
        _make_expired_order(out_trade_no="TOPUP_A"),
        _make_expired_order(out_trade_no="TOPUP_B"),
    ]
    _stub_scalars(patched_db, orders)

    result = close_expired_payment_orders()

    assert result == 2
    assert fake_service.close_order.call_count == 2
    fake_service.close_order.assert_any_call(tenant_id="t-1", out_trade_no="TOPUP_A")
    fake_service.close_order.assert_any_call(tenant_id="t-1", out_trade_no="TOPUP_B")


# ---------------------------------------------------------------------------
# OrderAlreadyClosed — continue silently, count doesn't include it
# ---------------------------------------------------------------------------


def test_skips_order_already_closed_race(
    patched_db: mock.MagicMock,
    patched_from_config: mock.MagicMock,
    fake_service: mock.MagicMock,
) -> None:
    orders = [
        _make_expired_order(out_trade_no="TOPUP_A"),
        _make_expired_order(out_trade_no="TOPUP_B"),
    ]
    _stub_scalars(patched_db, orders)
    # Second call raises — another worker closed it first.
    fake_service.close_order.side_effect = [
        None,
        OrderAlreadyClosed(status=PaymentOrderStatus.CLOSED.value),
    ]

    result = close_expired_payment_orders()

    assert result == 1
    assert fake_service.close_order.call_count == 2


# ---------------------------------------------------------------------------
# PaymentError (e.g. provider business error) — log & continue
# ---------------------------------------------------------------------------


def test_continues_past_payment_error(
    patched_db: mock.MagicMock,
    patched_from_config: mock.MagicMock,
    fake_service: mock.MagicMock,
) -> None:
    orders = [
        _make_expired_order(out_trade_no="TOPUP_A"),
        _make_expired_order(out_trade_no="TOPUP_B"),
        _make_expired_order(out_trade_no="TOPUP_C"),
    ]
    _stub_scalars(patched_db, orders)
    fake_service.close_order.side_effect = [
        None,
        ProviderBusinessError(code="40004", sub_code="ACQ.TRADE_NOT_EXIST"),
        None,
    ]

    result = close_expired_payment_orders()

    # 2 succeeded (A + C); B raised and was logged.
    assert result == 2
    assert fake_service.close_order.call_count == 3


def test_continues_past_order_not_found(
    patched_db: mock.MagicMock,
    patched_from_config: mock.MagicMock,
    fake_service: mock.MagicMock,
) -> None:
    orders = [
        _make_expired_order(out_trade_no="TOPUP_A"),
        _make_expired_order(out_trade_no="TOPUP_B"),
    ]
    _stub_scalars(patched_db, orders)
    fake_service.close_order.side_effect = [
        OrderNotFound(out_trade_no="TOPUP_A"),
        None,
    ]

    result = close_expired_payment_orders()

    assert result == 1
    assert fake_service.close_order.call_count == 2


# ---------------------------------------------------------------------------
# Unexpected Exception — logged, never propagated
# ---------------------------------------------------------------------------


def test_continues_past_unexpected_exception(
    patched_db: mock.MagicMock,
    patched_from_config: mock.MagicMock,
    fake_service: mock.MagicMock,
) -> None:
    orders = [
        _make_expired_order(out_trade_no="TOPUP_A"),
        _make_expired_order(out_trade_no="TOPUP_B"),
    ]
    _stub_scalars(patched_db, orders)
    fake_service.close_order.side_effect = [
        RuntimeError("db connection lost"),
        None,
    ]

    # Act — must not raise
    result = close_expired_payment_orders()

    assert result == 1
    assert fake_service.close_order.call_count == 2


# ---------------------------------------------------------------------------
# limit parameter reaches the SELECT
# ---------------------------------------------------------------------------


def test_passes_limit_to_query(
    patched_db: mock.MagicMock,
    patched_from_config: mock.MagicMock,
) -> None:
    _stub_scalars(patched_db, [])

    close_expired_payment_orders(limit=50)

    # Inspect the statement passed to scalars. Its compile text should contain LIMIT 50.
    stmt = patched_db.session.scalars.call_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT 50" in compiled.upper()


# ---------------------------------------------------------------------------
# Celery task metadata
# ---------------------------------------------------------------------------


def test_task_has_expected_name_and_queue() -> None:
    assert close_expired_payment_orders.name == "payment_order_expiry.close_expired"
