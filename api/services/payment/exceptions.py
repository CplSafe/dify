"""Domain exceptions raised by payment providers.

Concrete providers translate upstream business-level failures (e.g. Alipay's
``code != "10000"`` responses) into these structured errors so the
PaymentService and controllers can react without parsing raw SDK payloads.
"""

from __future__ import annotations


class PaymentError(Exception):
    """Base class for all payment-provider domain errors."""


class ProviderBusinessError(PaymentError):
    """Upstream provider returned a business-level failure.

    ``code`` is the top-level return code (e.g. ``"40004"``). ``sub_code`` /
    ``sub_msg`` are the Alipay-style detail fields (e.g.
    ``"ACQ.TRADE_HAS_CLOSED"``). All three are preserved so callers can log
    the full context or surface the ``sub_msg`` to operators.
    """

    def __init__(
        self,
        *,
        code: str,
        sub_code: str | None = None,
        sub_msg: str | None = None,
        message: str | None = None,
    ) -> None:
        self.code = code
        self.sub_code = sub_code
        self.sub_msg = sub_msg
        super().__init__(message or self._format_message())

    def _format_message(self) -> str:
        parts: list[str] = [f"code={self.code}"]
        if self.sub_code:
            parts.append(f"sub_code={self.sub_code}")
        if self.sub_msg:
            parts.append(f"sub_msg={self.sub_msg}")
        return "Alipay business error: " + ", ".join(parts)

    def __repr__(self) -> str:
        return f"ProviderBusinessError(code={self.code!r}, sub_code={self.sub_code!r}, sub_msg={self.sub_msg!r})"
