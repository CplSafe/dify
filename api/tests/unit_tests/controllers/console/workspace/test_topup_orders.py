"""Unit tests for the topup order console endpoints.

These cover:

- happy-path create / get / list / close
- error-mapping from ``PaymentService`` domain exceptions to stable
  ``BaseHTTPException`` subclasses with the documented HTTP codes

Router decorators (``@setup_required`` etc.) are no-op'd via module
reimport — same technique as ``test_load_balancing_config.py`` and
``test_topup_wallet.py``.
"""

from __future__ import annotations

import builtins
import importlib
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.views import MethodView

from services.payment.exceptions import (
    AmountTooLarge,
    AmountTooSmall,
    OrderAlreadyClosed,
    OrderNotFound,
    PaymentDisabled,
    ProviderBusinessError,
)

if not hasattr(builtins, "MethodView"):
    builtins.MethodView = MethodView  # type: ignore[attr-defined]


@pytest.fixture
def app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def topup_module(monkeypatch: pytest.MonkeyPatch):
    """Reload the topup controller with auth decorators no-oped."""
    from controllers.console import console_ns, wraps
    from libs import login

    def _noop(func):
        return func

    monkeypatch.setattr(login, "login_required", _noop)
    monkeypatch.setattr(wraps, "setup_required", _noop)
    monkeypatch.setattr(wraps, "account_initialization_required", _noop)
    monkeypatch.setattr(wraps, "tenant_owner_required", _noop)

    def _noop_route(*args, **kwargs):
        def _decorator(cls):
            return cls

        return _decorator

    monkeypatch.setattr(console_ns, "route", _noop_route)

    module_name = "controllers.console.workspace.topup"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _fake_order(
    *,
    out_trade_no: str = "TOPUP20260414ABCDEF01",
    status: str = "pending",
    amount_fen: int = 10000,
    qr_code: str | None = "https://qr.alipay.com/bax0001",
) -> MagicMock:
    order = MagicMock()
    order.id = "order-uuid"
    order.out_trade_no = out_trade_no
    order.provider = "alipay_qr"
    order.provider_trade_no = None
    order.tenant_id = "tenant-1"
    order.account_id = "acct-1"
    order.amount = Decimal(amount_fen) / Decimal(100)
    order.amount_fen = amount_fen
    order.subject = "钱包充值"
    order.status = status
    order.qr_code = qr_code
    order.paid_at = None
    order.expires_at = datetime(2026, 4, 14, 12, 15, 0)
    order.created_at = datetime(2026, 4, 14, 12, 0, 0)
    return order


def _install_current_account(module, monkeypatch, account_id="acct-1", tenant_id="tenant-1"):
    account = MagicMock()
    account.id = account_id
    monkeypatch.setattr(
        module, "current_account_with_tenant", lambda: (account, tenant_id)
    )


def _mock_payment_service(module, monkeypatch) -> MagicMock:
    service = MagicMock()
    monkeypatch.setattr(
        module.PaymentService, "from_config", classmethod(lambda cls: service)
    )
    return service


# ---------------------------------------------------------------------------
# POST /topup/orders — create
# ---------------------------------------------------------------------------


class TestCreateTopupOrder:
    def test_happy_path_returns_201_with_service_result(
        self, app, topup_module, monkeypatch
    ):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.create_order.return_value = {
            "order_id": "order-uuid",
            "out_trade_no": "TOPUP20260414ABCDEF01",
            "provider": "alipay_qr",
            "amount_fen": 10000,
            "qr_code": "https://qr.alipay.com/bax0001",
            "pay_url": None,
            "expires_at": "2026-04-14T12:15:00",
        }

        with app.test_request_context(
            "/",
            method="POST",
            json={"amount_fen": 10000, "subject": "钱包充值"},
            environ_base={"REMOTE_ADDR": "203.0.113.5"},
        ):
            body, status = topup_module.TopupOrderListApi().post()

        assert status == 201
        assert body["out_trade_no"] == "TOPUP20260414ABCDEF01"
        assert body["qr_code"] == "https://qr.alipay.com/bax0001"
        service.create_order.assert_called_once_with(
            tenant_id="tenant-1",
            account_id="acct-1",
            amount_fen=10000,
            subject="钱包充值",
            client_ip="203.0.113.5",
        )

    @pytest.mark.parametrize(
        "payload",
        [
            {},  # missing amount
            {"amount_fen": 0},  # must be > 0
            {"amount_fen": -1},
            {"amount_fen": 10_000_001},  # > max
            {"amount_fen": "100"},  # non-int
        ],
    )
    def test_invalid_payload_raises_400(self, app, topup_module, monkeypatch, payload):
        _install_current_account(topup_module, monkeypatch)
        _mock_payment_service(topup_module, monkeypatch)

        with app.test_request_context("/", method="POST", json=payload):
            with pytest.raises(topup_module.TopupAmountInvalidError) as exc:
                topup_module.TopupOrderListApi().post()
        assert exc.value.code == 400

    def test_payment_disabled_raises_503(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.create_order.side_effect = PaymentDisabled("disabled")

        with app.test_request_context("/", method="POST", json={"amount_fen": 10000}):
            with pytest.raises(topup_module.PaymentDisabledHTTPError) as exc:
                topup_module.TopupOrderListApi().post()
        assert exc.value.code == 503

    def test_amount_too_small_raises_400(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.create_order.side_effect = AmountTooSmall(amount_fen=50, min_fen=100)

        with app.test_request_context("/", method="POST", json={"amount_fen": 50}):
            with pytest.raises(topup_module.TopupAmountInvalidError) as exc:
                topup_module.TopupOrderListApi().post()
        assert exc.value.code == 400

    def test_amount_too_large_raises_400(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.create_order.side_effect = AmountTooLarge(
            amount_fen=99_999_999, max_fen=10_000_000
        )

        with app.test_request_context("/", method="POST", json={"amount_fen": 500000}):
            with pytest.raises(topup_module.TopupAmountInvalidError) as exc:
                topup_module.TopupOrderListApi().post()
        assert exc.value.code == 400

    def test_provider_business_error_raises_502(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.create_order.side_effect = ProviderBusinessError(
            code="40004", sub_code="ACQ.SYSTEM_ERROR", sub_msg="Alipay busy"
        )

        with app.test_request_context("/", method="POST", json={"amount_fen": 10000}):
            with pytest.raises(topup_module.TopupProviderError) as exc:
                topup_module.TopupOrderListApi().post()
        assert exc.value.code == 502


# ---------------------------------------------------------------------------
# GET /topup/orders — list
# ---------------------------------------------------------------------------


class TestListTopupOrders:
    def test_returns_paginated_orders(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.list_tenant_orders.return_value = ([_fake_order()], 1)

        with app.test_request_context("/?limit=10&offset=0"):
            body, status = topup_module.TopupOrderListApi().get()

        assert status == 200
        assert body == {
            "data": [
                {
                    "order_id": "order-uuid",
                    "out_trade_no": "TOPUP20260414ABCDEF01",
                    "provider": "alipay_qr",
                    "provider_trade_no": None,
                    "tenant_id": "tenant-1",
                    "account_id": "acct-1",
                    "amount": "100",
                    "amount_fen": 10000,
                    "subject": "钱包充值",
                    "status": "pending",
                    "qr_code": "https://qr.alipay.com/bax0001",
                    "paid_at": None,
                    "expires_at": "2026-04-14T12:15:00",
                    "created_at": "2026-04-14T12:00:00",
                }
            ],
            "total": 1,
            "limit": 10,
            "offset": 0,
        }
        service.list_tenant_orders.assert_called_once_with(
            tenant_id="tenant-1", limit=10, offset=0
        )

    def test_limit_is_capped_at_100(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.list_tenant_orders.return_value = ([], 0)

        with app.test_request_context("/?limit=9999"):
            topup_module.TopupOrderListApi().get()

        assert service.list_tenant_orders.call_args.kwargs["limit"] == 100


# ---------------------------------------------------------------------------
# GET /topup/orders/<out_trade_no>
# ---------------------------------------------------------------------------


class TestGetTopupOrder:
    def test_returns_200_on_found(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.get_order.return_value = _fake_order()

        with app.test_request_context("/"):
            body, status = topup_module.TopupOrderDetailApi().get("TOPUP20260414ABCDEF01")

        assert status == 200
        assert body["out_trade_no"] == "TOPUP20260414ABCDEF01"
        service.get_order.assert_called_once_with(
            tenant_id="tenant-1", out_trade_no="TOPUP20260414ABCDEF01"
        )

    def test_returns_404_on_missing(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.get_order.side_effect = OrderNotFound(out_trade_no="MISSING")

        with app.test_request_context("/"):
            with pytest.raises(topup_module.TopupOrderNotFoundError) as exc:
                topup_module.TopupOrderDetailApi().get("MISSING")
        assert exc.value.code == 404


# ---------------------------------------------------------------------------
# POST /topup/orders/<out_trade_no>/close
# ---------------------------------------------------------------------------


class TestCloseTopupOrder:
    def test_happy_path_returns_closed_order(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.close_order.return_value = _fake_order(status="closed")

        with app.test_request_context("/", method="POST"):
            body, status = topup_module.TopupOrderCloseApi().post(
                "TOPUP20260414ABCDEF01"
            )

        assert status == 200
        assert body["status"] == "closed"
        service.close_order.assert_called_once_with(
            tenant_id="tenant-1", out_trade_no="TOPUP20260414ABCDEF01"
        )

    def test_missing_order_returns_404(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.close_order.side_effect = OrderNotFound(out_trade_no="MISSING")

        with app.test_request_context("/", method="POST"):
            with pytest.raises(topup_module.TopupOrderNotFoundError) as exc:
                topup_module.TopupOrderCloseApi().post("MISSING")
        assert exc.value.code == 404

    def test_already_paid_returns_409(self, app, topup_module, monkeypatch):
        _install_current_account(topup_module, monkeypatch)
        service = _mock_payment_service(topup_module, monkeypatch)
        service.close_order.side_effect = OrderAlreadyClosed(status="paid")

        with app.test_request_context("/", method="POST"):
            with pytest.raises(topup_module.TopupOrderAlreadyClosedError) as exc:
                topup_module.TopupOrderCloseApi().post("TOPUP20260414ABCDEF01")
        assert exc.value.code == 409
