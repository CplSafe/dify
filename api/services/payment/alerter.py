"""Payment alerting — protocol + default logger implementation.

When a high-value payment order is created, we emit an alert so ops can
watch for fraud / abuse. The Protocol lets us swap the transport later
(email, Slack, Feishu) without touching PaymentService.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from models.creator import PaymentOrder

logger = logging.getLogger(__name__)


@runtime_checkable
class PaymentAlerter(Protocol):
    """Minimal contract for payment-related alerts.

    Implementations must be safe to call synchronously from inside a
    PaymentService request: failures should be logged internally, never
    propagated, so a flaky alert channel cannot break payment creation.
    """

    def alert_large_amount(self, order: PaymentOrder, threshold_fen: int) -> None: ...


class LoggingPaymentAlerter:
    """Default alerter — writes a WARNING-level log line.

    Suitable for dev and for production environments where a central
    logging pipeline (ELK / Loki) already surfaces WARN events to oncall.
    Swap for a MailPaymentAlerter etc. when stakeholder is decided.
    """

    name = "logging"

    def alert_large_amount(self, order: PaymentOrder, threshold_fen: int) -> None:
        try:
            logger.warning(
                "payment.large_amount_alert out_trade_no=%s tenant=%s account=%s "
                "amount_fen=%d threshold_fen=%d provider=%s",
                order.out_trade_no,
                order.tenant_id,
                order.account_id,
                order.amount_fen,
                threshold_fen,
                order.provider,
            )
        except Exception:
            logger.exception("LoggingPaymentAlerter failed to emit alert")


class NullPaymentAlerter:
    """No-op alerter for tests and for installations that want silence."""

    name = "null"

    def alert_large_amount(self, order: PaymentOrder, threshold_fen: int) -> None:
        return None
