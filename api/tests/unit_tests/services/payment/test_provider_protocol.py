"""Unit tests for the PaymentProvider protocol contract."""

from __future__ import annotations

from services.payment.provider import CreateOrderResult, PaymentProvider


class _FakeProvider:
    """A minimal duck-typed implementation used to verify Protocol conformance."""

    name: str = "alipay_qr"

    def create_order(
        self,
        *,
        out_trade_no: str,
        amount_fen: int,
        subject: str,
        timeout_express: str,
        client_ip: str | None = None,
    ) -> CreateOrderResult:
        return CreateOrderResult(
            qr_code="https://qr.alipay.com/bax00001",
            pay_url=None,
            provider_trade_no=None,
            raw='{"alipay_trade_precreate_response":{"code":"10000"}}',
        )

    def query_order(self, out_trade_no: str) -> dict:
        return {"trade_status": "WAIT_BUYER_PAY"}

    def close_order(self, out_trade_no: str) -> dict:
        return {"code": "10000"}

    def verify_notify(self, params: dict[str, str]) -> bool:
        return True


class _IncompleteProvider:
    """A provider that does NOT satisfy the Protocol (missing methods)."""

    name: str = "bad"


def test_fake_provider_satisfies_runtime_checkable_protocol() -> None:
    # Arrange
    provider = _FakeProvider()

    # Act / Assert
    assert isinstance(provider, PaymentProvider)


def test_incomplete_provider_does_not_satisfy_protocol() -> None:
    # Arrange
    provider = _IncompleteProvider()

    # Act / Assert
    assert not isinstance(provider, PaymentProvider)


def test_create_order_result_is_typed_dict_shape() -> None:
    # Arrange / Act
    result: CreateOrderResult = {
        "qr_code": None,
        "pay_url": "https://openapi.alipay.com/gateway.do?...",
        "provider_trade_no": None,
        "raw": "{}",
    }

    # Assert
    assert set(result.keys()) == {"qr_code", "pay_url", "provider_trade_no", "raw"}
