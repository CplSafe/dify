"""Alipay Page (``alipay.trade.page.pay``) payment provider.

Handles the **电脑网站支付** / PC web checkout channel: the backend asks
Alipay's SDK for a fully-signed GET URL, which the frontend then uses via
``window.location.href = pay_url`` to redirect the user to Alipay's hosted
cashier page.

Unlike QR / precreate, this channel is **not** a server-to-server JSON call —
``create_order`` does not hit Alipay over HTTP. The signed URL is generated
locally by :meth:`AlipayClient.web_pay_url` and returned to the caller.

This channel is used for larger-amount top-ups (PaymentService routes
``amount_fen > ALIPAY_QR_MAX_FEN`` here, up to
``ALIPAY_PAGE_MAX_FEN`` ≈ ¥100,000). Completion is confirmed via the
asynchronous ``notify_url`` callback — the synchronous ``return_url`` is
browser-side only and must NOT be trusted as proof of payment.

See ``.claude/skills/alipay-payment-integration/SKILL.md`` for the full
route table and Alipay's official docs for biz-param semantics.
"""

from __future__ import annotations

import json
from typing import Any

from services.payment._amount import fen_to_yuan_string
from services.payment.alipay_client import AlipayClient
from services.payment.provider import CreateOrderResult

# The ``product_code`` required by Alipay for PC web-checkout payments.
_PRODUCT_CODE_PAGE_PAY = "FAST_INSTANT_TRADE_PAY"


class AlipayPageProvider:
    """Alipay 电脑网站支付 (page.pay) channel implementation.

    Instantiate with a shared :class:`AlipayClient`; routing is performed by
    :class:`PaymentService` based on amount thresholds.
    """

    name: str = "alipay_page"

    def __init__(self, client: AlipayClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # PaymentProvider Protocol methods
    # ------------------------------------------------------------------

    def create_order(
        self,
        *,
        out_trade_no: str,
        amount_fen: int,
        subject: str,
        timeout_express: str,
        client_ip: str | None = None,
    ) -> CreateOrderResult:
        """Build a signed ``alipay.trade.page.pay`` redirect URL.

        ``amount_fen`` is converted to a 2-decimal yuan string via
        ``Decimal`` to avoid float rounding errors. ``client_ip`` — when
        supplied — is forwarded as ``business_params.mc_create_trade_ip`` so
        Alipay risk controls can see the originating client.

        Returns a :class:`CreateOrderResult` whose ``pay_url`` holds the
        signed URL. The ``raw`` field carries a JSON envelope
        (``{"pay_url": "..."}``) so it can be stored on
        ``PaymentOrder.prepay_raw`` without ambiguity vs. server-to-server
        responses, and so future audit logs keep a consistent shape.
        """
        biz_content: dict[str, Any] = {
            "out_trade_no": out_trade_no,
            "total_amount": fen_to_yuan_string(amount_fen),
            "subject": subject,
            "product_code": _PRODUCT_CODE_PAGE_PAY,
            "timeout_express": timeout_express,
        }
        if client_ip:
            biz_content["business_params"] = {"mc_create_trade_ip": client_ip}

        pay_url = self._client.web_pay_url(biz_content)

        return CreateOrderResult(
            qr_code=None,
            pay_url=pay_url,
            provider_trade_no=None,
            raw=json.dumps({"pay_url": pay_url}, ensure_ascii=False),
        )

    def query_order(self, out_trade_no: str) -> dict:
        """Query upstream status; returns the raw ``alipay.trade.query`` body."""
        return self._client.request("alipay.trade.query", {"out_trade_no": out_trade_no})

    def close_order(self, out_trade_no: str) -> dict:
        """Close an unpaid order via ``alipay.trade.close``."""
        return self._client.request("alipay.trade.close", {"out_trade_no": out_trade_no})

    def verify_notify(self, params: dict[str, str]) -> bool:
        """Delegate async-notify signature verification to the shared client."""
        return self._client.verify_notify(params)

    def __repr__(self) -> str:
        return f"AlipayPageProvider(client={self._client!r})"
