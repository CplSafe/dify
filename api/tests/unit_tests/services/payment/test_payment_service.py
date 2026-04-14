"""Unit tests for PaymentService (topup order lifecycle + routing + notify).

These tests mock the DB session and the two provider instances so they can
run without a Flask application context. The service's transactional
invariants (row-lock, single commit, idempotency) are exercised through
``db.session.add`` / ``db.session.commit`` call assertions.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from unittest import mock

import pytest

from models.creator import (
    BillingRecord,
    BillingRecordType,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentProviderName,
)
from services.payment.alerter import NullPaymentAlerter
from services.payment.exceptions import (
    AmountTooLarge,
    AmountTooSmall,
    OrderAlreadyClosed,
    OrderNotFound,
    PaymentDisabled,
    ProviderBusinessError,
)
from services.payment.payment_service import PaymentService
from services.payment.provider import CreateOrderResult

# ---------------------------------------------------------------------------
# Config constants used across tests
# ---------------------------------------------------------------------------

QR_MAX_FEN = 100_000  # ¥1,000
MIN_AMOUNT_FEN = 100  # ¥1
MAX_AMOUNT_FEN = 10_000_000  # ¥100,000
ORDER_TIMEOUT_MIN = 15
APP_ID = "2021000000000000"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def qr_provider() -> mock.MagicMock:
    p = mock.MagicMock()
    p.name = PaymentProviderName.ALIPAY_QR.value
    return p


@pytest.fixture
def page_provider() -> mock.MagicMock:
    p = mock.MagicMock()
    p.name = PaymentProviderName.ALIPAY_PAGE.value
    return p


@pytest.fixture
def service(qr_provider: mock.MagicMock, page_provider: mock.MagicMock) -> PaymentService:
    return PaymentService(
        qr_provider=qr_provider,
        page_provider=page_provider,
        qr_max_fen=QR_MAX_FEN,
        min_amount_fen=MIN_AMOUNT_FEN,
        max_amount_fen=MAX_AMOUNT_FEN,
        order_timeout_min=ORDER_TIMEOUT_MIN,
        enabled=True,
        expected_app_id=APP_ID,
    )


@pytest.fixture
def disabled_service(qr_provider: mock.MagicMock, page_provider: mock.MagicMock) -> PaymentService:
    return PaymentService(
        qr_provider=qr_provider,
        page_provider=page_provider,
        qr_max_fen=QR_MAX_FEN,
        min_amount_fen=MIN_AMOUNT_FEN,
        max_amount_fen=MAX_AMOUNT_FEN,
        order_timeout_min=ORDER_TIMEOUT_MIN,
        enabled=False,
        expected_app_id=APP_ID,
    )


def _qr_result(qr_code: str = "https://qr.alipay.com/bax_test") -> CreateOrderResult:
    return CreateOrderResult(
        qr_code=qr_code,
        pay_url=None,
        provider_trade_no=None,
        raw=f'{{"qr_code": "{qr_code}"}}',
    )


def _page_result(pay_url: str = "https://openapi.alipay.com/gateway.do?a=1") -> CreateOrderResult:
    return CreateOrderResult(
        qr_code=None,
        pay_url=pay_url,
        provider_trade_no=None,
        raw=f'{{"pay_url": "{pay_url}"}}',
    )


# ---------------------------------------------------------------------------
# create_order — validation
# ---------------------------------------------------------------------------


@mock.patch("services.payment.payment_service.db")
def test_create_order_raises_when_disabled(mock_db: mock.MagicMock, disabled_service: PaymentService) -> None:
    with pytest.raises(PaymentDisabled):
        disabled_service.create_order(
            tenant_id="t-1", account_id="a-1", amount_fen=500
        )
    mock_db.session.add.assert_not_called()


@mock.patch("services.payment.payment_service.db")
def test_create_order_rejects_below_minimum(mock_db: mock.MagicMock, service: PaymentService) -> None:
    with pytest.raises(AmountTooSmall) as excinfo:
        service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=MIN_AMOUNT_FEN - 1)
    assert excinfo.value.min_fen == MIN_AMOUNT_FEN
    assert excinfo.value.amount_fen == MIN_AMOUNT_FEN - 1
    mock_db.session.add.assert_not_called()


@mock.patch("services.payment.payment_service.db")
def test_create_order_rejects_above_maximum(mock_db: mock.MagicMock, service: PaymentService) -> None:
    with pytest.raises(AmountTooLarge) as excinfo:
        service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=MAX_AMOUNT_FEN + 1)
    assert excinfo.value.max_fen == MAX_AMOUNT_FEN
    mock_db.session.add.assert_not_called()


# ---------------------------------------------------------------------------
# create_order — routing
# ---------------------------------------------------------------------------


@mock.patch("services.payment.payment_service.db")
def test_create_order_small_amount_routes_to_qr(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
) -> None:
    # Arrange
    qr_provider.create_order.return_value = _qr_result()

    # Act
    result = service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=50_000)

    # Assert
    qr_provider.create_order.assert_called_once()
    page_provider.create_order.assert_not_called()
    assert result["provider"] == "alipay_qr"
    assert result["qr_code"] is not None
    assert result["pay_url"] is None


@mock.patch("services.payment.payment_service.db")
def test_create_order_large_amount_routes_to_page(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
) -> None:
    # Arrange
    page_provider.create_order.return_value = _page_result()

    # Act
    result = service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=200_000)

    # Assert
    page_provider.create_order.assert_called_once()
    qr_provider.create_order.assert_not_called()
    assert result["provider"] == "alipay_page"
    assert result["qr_code"] is None
    assert result["pay_url"] is not None


@mock.patch("services.payment.payment_service.db")
def test_create_order_at_qr_boundary_uses_qr(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
) -> None:
    """amount_fen == ALIPAY_QR_MAX_FEN stays on QR (<= boundary)."""
    qr_provider.create_order.return_value = _qr_result()

    result = service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=QR_MAX_FEN)

    assert result["provider"] == "alipay_qr"
    qr_provider.create_order.assert_called_once()
    page_provider.create_order.assert_not_called()


@mock.patch("services.payment.payment_service.db")
def test_create_order_one_fen_above_qr_boundary_uses_page(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
) -> None:
    page_provider.create_order.return_value = _page_result()

    result = service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=QR_MAX_FEN + 1)

    assert result["provider"] == "alipay_page"
    page_provider.create_order.assert_called_once()
    qr_provider.create_order.assert_not_called()


# ---------------------------------------------------------------------------
# create_order — upstream failure path
# ---------------------------------------------------------------------------


@mock.patch("services.payment.payment_service.db")
def test_create_order_upstream_business_error_marks_failed_and_reraises(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    # Arrange
    qr_provider.create_order.side_effect = ProviderBusinessError(
        code="40004", sub_code="ACQ.MERCHANT_STATUS_NOT_NORMAL"
    )

    # Act
    with pytest.raises(ProviderBusinessError):
        service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=50_000)

    # Assert — we should have added an order, then re-added it after marking FAILED
    added_orders = [
        call.args[0]
        for call in mock_db.session.add.call_args_list
        if isinstance(call.args[0], PaymentOrder)
    ]
    assert len(added_orders) >= 1
    # The last-added order carries the FAILED status.
    assert added_orders[-1].status == PaymentOrderStatus.FAILED.value


# ---------------------------------------------------------------------------
# create_order — happy-path payload shape
# ---------------------------------------------------------------------------


@mock.patch("services.payment.payment_service.db")
def test_create_order_returns_well_formed_payload(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    # Arrange
    qr_provider.create_order.return_value = _qr_result("https://qr.alipay.com/bax_happy")

    # Act
    result = service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=50_000)

    # Assert
    assert result["amount_fen"] == 50_000
    assert result["qr_code"] == "https://qr.alipay.com/bax_happy"
    assert result["pay_url"] is None
    assert result["provider"] == "alipay_qr"
    assert result["out_trade_no"].startswith("TOPUP")
    # expires_at is ISO-formatted
    assert "T" in result["expires_at"]


@mock.patch("services.payment.payment_service.db")
def test_create_order_generates_expected_out_trade_no_shape(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    # Arrange
    qr_provider.create_order.return_value = _qr_result()

    # Act
    result = service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=50_000)

    # Assert — TOPUP + 8 date digits + 8 uppercase hex chars
    assert re.fullmatch(r"TOPUP\d{8}[0-9A-F]{8}", result["out_trade_no"])


@mock.patch("services.payment.payment_service.db")
def test_create_order_passes_custom_subject_to_provider(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    qr_provider.create_order.return_value = _qr_result()

    service.create_order(
        tenant_id="t-1",
        account_id="a-1",
        amount_fen=50_000,
        subject="Pro plan topup",
    )

    kwargs = qr_provider.create_order.call_args.kwargs
    assert kwargs["subject"] == "Pro plan topup"
    assert kwargs["timeout_express"] == f"{ORDER_TIMEOUT_MIN}m"


@mock.patch("services.payment.payment_service.db")
def test_create_order_forwards_client_ip(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    qr_provider.create_order.return_value = _qr_result()

    service.create_order(
        tenant_id="t-1",
        account_id="a-1",
        amount_fen=50_000,
        client_ip="203.0.113.42",
    )

    kwargs = qr_provider.create_order.call_args.kwargs
    assert kwargs["client_ip"] == "203.0.113.42"


# ---------------------------------------------------------------------------
# handle_notify — rejection paths
# ---------------------------------------------------------------------------


def _make_order(
    *,
    out_trade_no: str = "TOPUP20260414ABCD1234",
    tenant_id: str = "t-1",
    account_id: str = "a-1",
    amount: Decimal = Decimal("5.00"),
    amount_fen: int = 500,
    status: str = PaymentOrderStatus.PENDING.value,
    provider: str = PaymentProviderName.ALIPAY_QR.value,
) -> PaymentOrder:
    order = PaymentOrder(
        provider=provider,
        out_trade_no=out_trade_no,
        tenant_id=tenant_id,
        account_id=account_id,
        amount=amount,
        amount_fen=amount_fen,
        subject="test",
    )
    order.status = status
    return order


def _notify_params(
    *,
    out_trade_no: str = "TOPUP20260414ABCD1234",
    total_amount: str = "5.00",
    trade_status: str = "TRADE_SUCCESS",
    trade_no: str = "2026041422001400000012345",
    app_id: str = APP_ID,
) -> dict[str, str]:
    return {
        "out_trade_no": out_trade_no,
        "total_amount": total_amount,
        "trade_status": trade_status,
        "trade_no": trade_no,
        "app_id": app_id,
        "sign": "fake-sig",
    }


@mock.patch("services.payment.payment_service.db")
def test_notify_missing_out_trade_no_returns_false(
    mock_db: mock.MagicMock, service: PaymentService
) -> None:
    assert service.handle_notify({"trade_status": "TRADE_SUCCESS"}) is False
    mock_db.session.commit.assert_not_called()


@mock.patch("services.payment.payment_service.db")
def test_notify_order_not_found_returns_false(
    mock_db: mock.MagicMock, service: PaymentService
) -> None:
    mock_db.session.scalar.return_value = None

    assert service.handle_notify(_notify_params()) is False
    mock_db.session.commit.assert_not_called()


@mock.patch("services.payment.payment_service.db")
def test_notify_bad_signature_returns_false(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    order = _make_order()
    mock_db.session.scalar.return_value = order
    qr_provider.verify_notify.return_value = False

    assert service.handle_notify(_notify_params()) is False
    mock_db.session.commit.assert_not_called()


@mock.patch("services.payment.payment_service.db")
def test_notify_wrong_app_id_returns_false(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    order = _make_order()
    mock_db.session.scalar.return_value = order
    qr_provider.verify_notify.return_value = True

    params = _notify_params(app_id="attacker-app-id")
    assert service.handle_notify(params) is False
    mock_db.session.commit.assert_not_called()


@mock.patch("services.payment.payment_service.db")
def test_notify_amount_mismatch_returns_false(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    # Order is ¥5.00 but notify claims ¥5000.00.
    order = _make_order(amount=Decimal("5.00"), amount_fen=500)
    mock_db.session.scalar.return_value = order
    qr_provider.verify_notify.return_value = True

    params = _notify_params(total_amount="5000.00")
    assert service.handle_notify(params) is False
    mock_db.session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# handle_notify — idempotency
# ---------------------------------------------------------------------------


@mock.patch("services.payment.payment_service.db")
def test_notify_already_paid_is_idempotent(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    order = _make_order(status=PaymentOrderStatus.PAID.value)
    mock_db.session.scalar.return_value = order
    qr_provider.verify_notify.return_value = True

    assert service.handle_notify(_notify_params()) is True
    # Must not re-credit the wallet.
    mock_db.session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# handle_notify — trade_status branches
# ---------------------------------------------------------------------------


@mock.patch("services.payment.payment_service.TenantBalanceService")
@mock.patch("services.payment.payment_service.db")
def test_notify_wait_buyer_pay_is_noop_ack(
    mock_db: mock.MagicMock,
    mock_tbs: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    order = _make_order()
    mock_db.session.scalar.return_value = order
    qr_provider.verify_notify.return_value = True

    params = _notify_params(trade_status="WAIT_BUYER_PAY")
    assert service.handle_notify(params) is True
    mock_tbs.topup.assert_not_called()
    mock_db.session.commit.assert_not_called()


@mock.patch("services.payment.payment_service.TenantBalanceService")
@mock.patch("services.payment.payment_service.db")
def test_notify_trade_closed_marks_order_closed(
    mock_db: mock.MagicMock,
    mock_tbs: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    order = _make_order()
    mock_db.session.scalar.return_value = order
    qr_provider.verify_notify.return_value = True

    params = _notify_params(trade_status="TRADE_CLOSED")
    assert service.handle_notify(params) is True
    assert order.status == PaymentOrderStatus.CLOSED.value
    mock_tbs.topup.assert_not_called()
    mock_db.session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# handle_notify — happy paths
# ---------------------------------------------------------------------------


@mock.patch("services.payment.payment_service.TenantBalanceService")
@mock.patch("services.payment.payment_service.db")
def test_notify_trade_success_credits_wallet_and_writes_billing(
    mock_db: mock.MagicMock,
    mock_tbs: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    # Arrange
    order = _make_order(amount=Decimal("5.00"), amount_fen=500)
    mock_db.session.scalar.return_value = order
    qr_provider.verify_notify.return_value = True

    # Act
    result = service.handle_notify(_notify_params(trade_status="TRADE_SUCCESS"))

    # Assert
    assert result is True
    assert order.status == PaymentOrderStatus.PAID.value
    assert order.provider_trade_no == "2026041422001400000012345"
    assert order.paid_at is not None
    assert order.notify_raw is not None

    mock_tbs.topup.assert_called_once_with(tenant_id="t-1", amount=Decimal("5.00"))

    added_billing = [
        call.args[0]
        for call in mock_db.session.add.call_args_list
        if isinstance(call.args[0], BillingRecord)
    ]
    assert len(added_billing) == 1
    billing = added_billing[0]
    assert billing.account_id == "a-1"  # the owner who initiated the topup
    assert billing.tenant_id == "t-1"
    assert billing.amount == Decimal("5.00")
    assert billing.scope == "tenant"
    assert billing.record_type == BillingRecordType.TOPUP.value

    mock_db.session.commit.assert_called_once()


@mock.patch("services.payment.payment_service.TenantBalanceService")
@mock.patch("services.payment.payment_service.db")
def test_notify_trade_finished_also_credits_wallet(
    mock_db: mock.MagicMock,
    mock_tbs: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    order = _make_order()
    mock_db.session.scalar.return_value = order
    qr_provider.verify_notify.return_value = True

    result = service.handle_notify(_notify_params(trade_status="TRADE_FINISHED"))

    assert result is True
    mock_tbs.topup.assert_called_once()
    assert order.status == PaymentOrderStatus.PAID.value


@mock.patch("services.payment.payment_service.TenantBalanceService")
@mock.patch("services.payment.payment_service.db")
def test_notify_routes_to_page_provider_when_order_is_page(
    mock_db: mock.MagicMock,
    mock_tbs: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
) -> None:
    """An order stored with provider=alipay_page must verify through the page provider."""
    order = _make_order(provider=PaymentProviderName.ALIPAY_PAGE.value)
    mock_db.session.scalar.return_value = order
    page_provider.verify_notify.return_value = True

    result = service.handle_notify(_notify_params())

    assert result is True
    page_provider.verify_notify.assert_called_once()
    qr_provider.verify_notify.assert_not_called()


# ---------------------------------------------------------------------------
# get_order / list_tenant_orders / close_order
# ---------------------------------------------------------------------------


@mock.patch("services.payment.payment_service.db")
def test_get_order_returns_matching_row(mock_db: mock.MagicMock, service: PaymentService) -> None:
    order = _make_order()
    mock_db.session.scalar.return_value = order

    assert service.get_order(tenant_id="t-1", out_trade_no=order.out_trade_no) is order


@mock.patch("services.payment.payment_service.db")
def test_get_order_raises_when_missing(mock_db: mock.MagicMock, service: PaymentService) -> None:
    mock_db.session.scalar.return_value = None

    with pytest.raises(OrderNotFound) as excinfo:
        service.get_order(tenant_id="t-1", out_trade_no="MISSING")
    assert excinfo.value.out_trade_no == "MISSING"


@mock.patch("services.payment.payment_service.db")
def test_get_order_is_tenant_scoped(mock_db: mock.MagicMock, service: PaymentService) -> None:
    """A different tenant asking for someone else's order gets OrderNotFound.

    Relies on the WHERE clause including tenant_id — mock returns None.
    """
    mock_db.session.scalar.return_value = None

    with pytest.raises(OrderNotFound):
        service.get_order(tenant_id="t-attacker", out_trade_no="TOPUP20260414ABCD1234")


@mock.patch("services.payment.payment_service.select")
@mock.patch("services.payment.payment_service.db")
def test_list_tenant_orders_returns_rows_and_count(
    mock_db: mock.MagicMock,
    mock_select: mock.MagicMock,
    service: PaymentService,
) -> None:
    """Both the list and the total COUNT are returned to the caller."""
    # Arrange
    o1 = _make_order(out_trade_no="TOPUP_A")
    o2 = _make_order(out_trade_no="TOPUP_B")
    # scalar() is called twice: first for COUNT, then (inside list_tenant_orders)
    # only once — the rows themselves are pulled via scalars().all().
    mock_db.session.scalar.return_value = 2  # total count
    scalars_result = mock.MagicMock()
    scalars_result.all.return_value = [o1, o2]
    mock_db.session.scalars.return_value = scalars_result

    # Act
    rows, total = service.list_tenant_orders(tenant_id="t-1")

    # Assert
    assert rows == [o1, o2]
    assert total == 2
    # We issued two scalar() calls: one for count, and select() was called twice
    # (base query + count wrapper) to build them.
    assert mock_db.session.scalar.call_count == 1
    assert mock_db.session.scalars.call_count == 1


@mock.patch("services.payment.payment_service.db")
def test_close_order_rejects_non_pending(
    mock_db: mock.MagicMock, service: PaymentService
) -> None:
    order = _make_order(status=PaymentOrderStatus.PAID.value)
    mock_db.session.scalar.return_value = order

    with pytest.raises(OrderAlreadyClosed) as excinfo:
        service.close_order(tenant_id="t-1", out_trade_no=order.out_trade_no)
    assert excinfo.value.status == PaymentOrderStatus.PAID.value


@mock.patch("services.payment.payment_service.db")
def test_close_order_happy_path(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    order = _make_order()
    mock_db.session.scalar.return_value = order
    qr_provider.close_order.return_value = {"code": "10000"}

    result = service.close_order(tenant_id="t-1", out_trade_no=order.out_trade_no)

    assert result.status == PaymentOrderStatus.CLOSED.value
    qr_provider.close_order.assert_called_once_with(order.out_trade_no)
    mock_db.session.commit.assert_called_once()


@mock.patch("services.payment.payment_service.db")
def test_close_order_swallows_upstream_business_error(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    """Upstream close can legitimately fail (e.g. order never reached Alipay);
    we still close locally."""
    order = _make_order()
    mock_db.session.scalar.return_value = order
    qr_provider.close_order.side_effect = ProviderBusinessError(
        code="40004", sub_code="ACQ.TRADE_NOT_EXIST"
    )

    result = service.close_order(tenant_id="t-1", out_trade_no=order.out_trade_no)

    assert result.status == PaymentOrderStatus.CLOSED.value
    mock_db.session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# _route helper
# ---------------------------------------------------------------------------


def test_route_at_and_below_qr_max_uses_qr(service: PaymentService, qr_provider: mock.MagicMock) -> None:
    assert service._route(0) is qr_provider
    assert service._route(1) is qr_provider
    assert service._route(QR_MAX_FEN) is qr_provider


def test_route_above_qr_max_uses_page(service: PaymentService, page_provider: mock.MagicMock) -> None:
    assert service._route(QR_MAX_FEN + 1) is page_provider
    assert service._route(MAX_AMOUNT_FEN) is page_provider


# ---------------------------------------------------------------------------
# _amounts_match helper (covers the edge of tampered/missing payloads)
# ---------------------------------------------------------------------------


def test_amounts_match_handles_missing_and_malformed() -> None:
    assert PaymentService._amounts_match("5.00", Decimal("5.00")) is True
    assert PaymentService._amounts_match("5.0", Decimal("5.00")) is True
    assert PaymentService._amounts_match("5.01", Decimal("5.00")) is False
    assert PaymentService._amounts_match(None, Decimal("5.00")) is False
    assert PaymentService._amounts_match("not-a-number", Decimal("5.00")) is False


# ---------------------------------------------------------------------------
# Smoke: TypedDict response is a regular dict at runtime
# ---------------------------------------------------------------------------


@mock.patch("services.payment.payment_service.db")
def test_create_order_response_is_mapping_compatible(
    mock_db: mock.MagicMock,
    service: PaymentService,
    qr_provider: mock.MagicMock,
) -> None:
    qr_provider.create_order.return_value = _qr_result()

    result: Any = service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=50_000)

    # Exhaustive key check so downstream API schemas can rely on the shape.
    for key in ("order_id", "out_trade_no", "provider", "amount_fen", "qr_code", "pay_url", "expires_at"):
        assert key in result


# ---------------------------------------------------------------------------
# create_order — large amount alerter integration
# ---------------------------------------------------------------------------


ALERT_THRESHOLD_FEN = 5_000  # ¥50


def _service_with_alerter(
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
    alerter: mock.MagicMock,
    *,
    threshold_fen: int = ALERT_THRESHOLD_FEN,
) -> PaymentService:
    return PaymentService(
        qr_provider=qr_provider,
        page_provider=page_provider,
        qr_max_fen=QR_MAX_FEN,
        min_amount_fen=MIN_AMOUNT_FEN,
        max_amount_fen=MAX_AMOUNT_FEN,
        order_timeout_min=ORDER_TIMEOUT_MIN,
        enabled=True,
        expected_app_id=APP_ID,
        alerter=alerter,
        large_amount_threshold_fen=threshold_fen,
    )


@mock.patch("services.payment.payment_service.db")
def test_create_order_fires_alert_at_exactly_threshold(
    mock_db: mock.MagicMock,
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
) -> None:
    # Arrange
    qr_provider.create_order.return_value = _qr_result()
    alerter = mock.MagicMock(spec=NullPaymentAlerter)
    service = _service_with_alerter(qr_provider, page_provider, alerter)

    # Act
    service.create_order(tenant_id="t-1", account_id="a-1", amount_fen=ALERT_THRESHOLD_FEN)

    # Assert
    alerter.alert_large_amount.assert_called_once()
    call_args = alerter.alert_large_amount.call_args
    order_arg = call_args.args[0]
    assert isinstance(order_arg, PaymentOrder)
    assert order_arg.amount_fen == ALERT_THRESHOLD_FEN
    assert call_args.args[1] == ALERT_THRESHOLD_FEN


@mock.patch("services.payment.payment_service.db")
def test_create_order_fires_alert_above_threshold(
    mock_db: mock.MagicMock,
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
) -> None:
    qr_provider.create_order.return_value = _qr_result()
    alerter = mock.MagicMock(spec=NullPaymentAlerter)
    service = _service_with_alerter(qr_provider, page_provider, alerter)

    service.create_order(
        tenant_id="t-1", account_id="a-1", amount_fen=ALERT_THRESHOLD_FEN + 1
    )

    alerter.alert_large_amount.assert_called_once()


@mock.patch("services.payment.payment_service.db")
def test_create_order_skips_alert_below_threshold(
    mock_db: mock.MagicMock,
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
) -> None:
    qr_provider.create_order.return_value = _qr_result()
    alerter = mock.MagicMock(spec=NullPaymentAlerter)
    service = _service_with_alerter(qr_provider, page_provider, alerter)

    service.create_order(
        tenant_id="t-1", account_id="a-1", amount_fen=ALERT_THRESHOLD_FEN - 1
    )

    alerter.alert_large_amount.assert_not_called()


@mock.patch("services.payment.payment_service.db")
def test_create_order_succeeds_when_alerter_raises(
    mock_db: mock.MagicMock,
    qr_provider: mock.MagicMock,
    page_provider: mock.MagicMock,
) -> None:
    """A flaky alerter channel must not break payment creation."""
    qr_provider.create_order.return_value = _qr_result()
    alerter = mock.MagicMock(spec=NullPaymentAlerter)
    alerter.alert_large_amount.side_effect = RuntimeError("SMTP unavailable")
    service = _service_with_alerter(qr_provider, page_provider, alerter)

    # Act — should NOT raise
    result = service.create_order(
        tenant_id="t-1", account_id="a-1", amount_fen=ALERT_THRESHOLD_FEN * 2
    )

    # Assert — order was created successfully
    assert result["amount_fen"] == ALERT_THRESHOLD_FEN * 2
    assert result["out_trade_no"].startswith("TOPUP")
    alerter.alert_large_amount.assert_called_once()
