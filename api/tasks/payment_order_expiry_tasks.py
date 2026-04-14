"""Periodic cleanup of expired payment orders.

Any PaymentOrder still in PENDING state whose expires_at has passed is
closed locally (and best-effort upstream via alipay.trade.close). This
keeps the frontend from showing stale QR codes and prevents the order
list from growing unbounded with never-paid rows.
"""

import logging

from celery import shared_task
from sqlalchemy import select

from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.creator import PaymentOrder, PaymentOrderStatus
from services.payment.exceptions import OrderAlreadyClosed, PaymentError
from services.payment.payment_service import PaymentService

logger = logging.getLogger(__name__)


@shared_task(name="payment_order_expiry.close_expired", queue="schedule_executor")
def close_expired_payment_orders(limit: int = 200) -> int:
    """Close up to ``limit`` expired PENDING orders. Returns count closed."""
    now = naive_utc_now()
    stmt = (
        select(PaymentOrder)
        .where(
            PaymentOrder.status == PaymentOrderStatus.PENDING.value,
            PaymentOrder.expires_at.is_not(None),
            PaymentOrder.expires_at <= now,
        )
        .order_by(PaymentOrder.expires_at.asc())
        .limit(limit)
    )
    expired = list(db.session.scalars(stmt).all())
    if not expired:
        return 0

    service = PaymentService.from_config()
    closed = 0
    for order in expired:
        try:
            service.close_order(tenant_id=order.tenant_id, out_trade_no=order.out_trade_no)
            closed += 1
        except OrderAlreadyClosed:
            # Race with another worker or a user-triggered close — fine.
            continue
        except PaymentError:
            logger.exception(
                "Failed to close expired order out_trade_no=%s", order.out_trade_no
            )
        except Exception:
            logger.exception(
                "Unexpected error closing expired order out_trade_no=%s",
                order.out_trade_no,
            )
    logger.info("payment_order_expiry closed=%d scanned=%d", closed, len(expired))
    return closed
