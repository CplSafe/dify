"""Unit tests for the Alipay async notify endpoint.

Alipay calls this URL after every payment lifecycle event. The endpoint
delegates to ``PaymentService.handle_notify`` which handles signature
verification + idempotency. We only test the HTTP plumbing here:

- success/fail mapped from the bool return as plain text
- form-encoded body parsed to dict
- crashes return ``"fail"`` so Alipay retries (but no 500 leaks out)
- empty body short-circuits to ``"fail"``
"""

from __future__ import annotations

import builtins
import importlib
import sys
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.views import MethodView

if not hasattr(builtins, "MethodView"):
    builtins.MethodView = MethodView  # type: ignore[attr-defined]


@pytest.fixture
def app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def payment_module(monkeypatch: pytest.MonkeyPatch):
    """Reimport the module with the namespace route decorator no-op'd."""
    from controllers.inner_api import inner_api_ns

    def _noop_route(*args, **kwargs):
        def _decorator(cls):
            return cls

        return _decorator

    monkeypatch.setattr(inner_api_ns, "route", _noop_route)

    module_name = "controllers.inner_api.payment"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _mock_service(payment_module, monkeypatch) -> MagicMock:
    service = MagicMock()
    monkeypatch.setattr(
        payment_module.PaymentService,
        "from_config",
        classmethod(lambda cls: service),
    )
    return service


class TestAlipayNotifyApi:
    def test_form_body_success(self, app, payment_module, monkeypatch):
        """Happy path: form-encoded body -> service ok -> 200 'success'."""
        service = _mock_service(payment_module, monkeypatch)
        service.handle_notify.return_value = True

        with app.test_request_context(
            "/",
            method="POST",
            data={"out_trade_no": "TOPUP123", "trade_status": "TRADE_SUCCESS"},
            content_type="application/x-www-form-urlencoded",
        ):
            response = payment_module.AlipayNotifyApi().post()

        assert response.status_code == 200
        assert response.mimetype == "text/plain"
        assert response.get_data(as_text=True) == "success"
        service.handle_notify.assert_called_once_with(
            {"out_trade_no": "TOPUP123", "trade_status": "TRADE_SUCCESS"}
        )

    def test_form_body_fail_returns_fail_text(self, app, payment_module, monkeypatch):
        """Service rejects (bad signature etc.) -> 200 'fail' so Alipay retries."""
        service = _mock_service(payment_module, monkeypatch)
        service.handle_notify.return_value = False

        with app.test_request_context(
            "/",
            method="POST",
            data={"out_trade_no": "TOPUP123", "sign": "wrong"},
            content_type="application/x-www-form-urlencoded",
        ):
            response = payment_module.AlipayNotifyApi().post()

        assert response.status_code == 200
        assert response.get_data(as_text=True) == "fail"

    def test_empty_body_returns_fail_without_calling_service(
        self, app, payment_module, monkeypatch
    ):
        """Empty body never reaches the service — short-circuit to 'fail'."""
        service = _mock_service(payment_module, monkeypatch)

        with app.test_request_context("/", method="POST", data={}):
            response = payment_module.AlipayNotifyApi().post()

        assert response.get_data(as_text=True) == "fail"
        service.handle_notify.assert_not_called()

    def test_service_exception_returns_fail_not_500(
        self, app, payment_module, monkeypatch
    ):
        """A bug in handle_notify must NOT bubble to a 500 — return 'fail'."""
        service = _mock_service(payment_module, monkeypatch)
        service.handle_notify.side_effect = RuntimeError("oops")

        with app.test_request_context(
            "/",
            method="POST",
            data={"out_trade_no": "TOPUP123"},
            content_type="application/x-www-form-urlencoded",
        ):
            response = payment_module.AlipayNotifyApi().post()

        assert response.status_code == 200
        assert response.get_data(as_text=True) == "fail"

    def test_json_body_supported_for_local_testing(
        self, app, payment_module, monkeypatch
    ):
        """JSON body works too (local manual testing convenience)."""
        service = _mock_service(payment_module, monkeypatch)
        service.handle_notify.return_value = True

        with app.test_request_context(
            "/",
            method="POST",
            json={"out_trade_no": "TOPUP123", "trade_status": "TRADE_SUCCESS"},
        ):
            response = payment_module.AlipayNotifyApi().post()

        assert response.get_data(as_text=True) == "success"
        service.handle_notify.assert_called_once()
