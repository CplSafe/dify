"""Alipay QR (``alipay.trade.precreate``) payment provider.

Handles the **订单码支付** / "order code" channel: the backend calls
``alipay.trade.precreate`` to obtain a ``qr_code`` URL which the frontend
renders as a QR code for the user to scan with the Alipay app.

This channel is typically used for small-amount top-ups (PaymentService
routes ``amount_fen <= ALIPAY_QR_MAX_FEN`` here). Payment completion is
confirmed via the asynchronous notify callback rather than the return of
this call — ``create_order`` only delivers a QR code, the upstream
``trade_no`` is not returned until notify/query.

See ``.claude/skills/alipay-payment-integration/SKILL.md`` for the full
route table and Alipay's official docs for biz-param semantics.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from services.payment.alipay_client import AlipayClient
from services.payment.exceptions import ProviderBusinessError
from services.payment.provider import CreateOrderResult

# The ``product_code`` required by Alipay for QR-code (order-code) payments.
_PRODUCT_CODE_QR_OFFLINE = "QR_CODE_OFFLINE"

# Upstream top-level success code per the Alipay spec.
_CODE_SUCCESS = "10000"

# Quantum used to normalise yuan amounts to two decimal places ("12.34").
_YUAN_QUANTUM = Decimal("0.01")

# One yuan = 100 fen.
_FEN_PER_YUAN = Decimal(100)


class AlipayQrProvider:
    """Alipay 当面付 (QR / precreate) channel implementation.

    Instantiate with a shared :class:`AlipayClient`; routing is performed by
    :class:`PaymentService` based on amount thresholds.
    """

    name: str = "alipay_qr"

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
        """Call ``alipay.trade.precreate`` and return the QR code URL.

        ``amount_fen`` is converted to a 2-decimal yuan string via
        ``Decimal`` to avoid float rounding errors. ``client_ip`` — when
        supplied — is forwarded as ``business_params.mc_create_trade_ip`` so
        Alipay risk controls can see the originating client.
        """
        biz_content: dict[str, Any] = {
            "out_trade_no": out_trade_no,
            "total_amount": self._fen_to_yuan_string(amount_fen),
            "subject": subject,
            "product_code": _PRODUCT_CODE_QR_OFFLINE,
            "timeout_express": timeout_express,
        }
        if client_ip:
            biz_content["business_params"] = {"mc_create_trade_ip": client_ip}

        response = self._client.request("alipay.trade.precreate", biz_content)
        self._raise_on_business_failure(response)

        return CreateOrderResult(
            qr_code=response.get("qr_code"),
            pay_url=None,
            provider_trade_no=None,
            raw=json.dumps(response, ensure_ascii=False),
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fen_to_yuan_string(amount_fen: int) -> str:
        """Convert an integer fen amount to Alipay's yuan string format.

        Examples
        --------
        >>> AlipayQrProvider._fen_to_yuan_string(1234)
        '12.34'
        >>> AlipayQrProvider._fen_to_yuan_string(1)
        '0.01'
        """
        yuan = (Decimal(amount_fen) / _FEN_PER_YUAN).quantize(_YUAN_QUANTUM)
        return format(yuan, "f")

    @staticmethod
    def _raise_on_business_failure(response: dict[str, Any]) -> None:
        """Translate an Alipay business-error response into a domain error.

        Per Alipay's spec, ``code == "10000"`` means success. Anything else —
        including the absence of ``code``, which indicates a malformed
        upstream response — is raised as :class:`ProviderBusinessError` so
        callers can short-circuit without parsing raw SDK payloads.
        """
        code = response.get("code")
        if code == _CODE_SUCCESS:
            return

        raise ProviderBusinessError(
            code=str(code) if code is not None else "UNKNOWN",
            sub_code=response.get("sub_code"),
            sub_msg=response.get("sub_msg") or response.get("msg"),
        )

    def __repr__(self) -> str:
        return f"AlipayQrProvider(client={self._client!r})"
