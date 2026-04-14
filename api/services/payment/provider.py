"""Payment provider Protocol and shared DTOs.

Concrete providers (``AlipayQrProvider``, ``AlipayPageProvider``, etc.) expose
the uniform interface declared here so that :class:`PaymentService` can route
requests by channel without needing to know the underlying API shape.

Only the Protocol / TypedDict live in this module — avoid importing Flask,
httpx or SQLAlchemy here so that unit tests can exercise the abstraction
without pulling the full application context.
"""

from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class CreateOrderResult(TypedDict):
    """Result of calling ``create_order`` on a payment provider.

    Fields are channel-dependent:

    - ``qr_code``: present for alipay_qr (QR code URL the user scans).
    - ``pay_url``: present for alipay_page (redirect URL / form HTML).
    - ``provider_trade_no``: upstream trade identifier when the provider
      returns one up-front (Alipay generally omits this until notify/query).
    - ``raw``: the full upstream response payload (JSON string) to be
      persisted on ``PaymentOrder.prepay_raw`` for audit / debugging.
    """

    qr_code: str | None
    pay_url: str | None
    provider_trade_no: str | None
    raw: str


@runtime_checkable
class PaymentProvider(Protocol):
    """Uniform interface every payment channel must implement.

    The Protocol is ``@runtime_checkable`` so ``isinstance(provider, PaymentProvider)``
    can act as a smoke test in the provider registry — but prefer structural
    typing in annotations over runtime checks.
    """

    name: str

    def create_order(
        self,
        *,
        out_trade_no: str,
        amount_fen: int,
        subject: str,
        timeout_express: str,
        client_ip: str | None = None,
    ) -> CreateOrderResult:
        """Create an upstream order and return a user-facing redirect artifact."""
        ...

    def query_order(self, out_trade_no: str) -> dict:
        """Query upstream order status; returns the decoded response body."""
        ...

    def close_order(self, out_trade_no: str) -> dict:
        """Close an unpaid upstream order; returns the decoded response body."""
        ...

    def verify_notify(self, params: dict[str, str]) -> bool:
        """Verify an asynchronous notification callback.

        Signature validation only — callers remain responsible for replay
        protection, amount/app_id cross-checks and state transitions.
        """
        ...
