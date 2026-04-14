"""Topup order lifecycle service.

Orchestrates payment-order creation, channel routing, and async-notify
handling for workspace wallet top-ups. Acts as the seam between the HTTP
controllers (Phase 4) and the payment-provider layer (Phase 3.2 / 3.3).

Key invariants
--------------
- Only the workspace **owner** may top up. Role enforcement happens in the
  controller; this service trusts its ``account_id`` / ``tenant_id`` inputs.
- Notify handling is **idempotent**: a replayed notify for an already-PAID
  order returns ``True`` without re-crediting the wallet.
- Wallet crediting, PaymentOrder status update and BillingRecord insert all
  happen inside a single DB commit so partial credits are impossible.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import timedelta
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import select

from configs import dify_config
from libs.datetime_utils import naive_utc_now
from models.creator import (
    BillingRecord,
    BillingRecordType,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentProviderName,
)
from models.engine import db
from services.payment.alerter import LoggingPaymentAlerter, PaymentAlerter
from services.payment.alipay_client import AlipayClient
from services.payment.alipay_page_provider import AlipayPageProvider
from services.payment.alipay_qr_provider import AlipayQrProvider
from services.payment.exceptions import (
    AmountTooLarge,
    AmountTooSmall,
    OrderAlreadyClosed,
    OrderNotFound,
    PaymentDisabled,
    ProviderBusinessError,
)
from services.payment.provider import PaymentProvider
from services.wallet.tenant_balance_service import TenantBalanceService

logger = logging.getLogger(__name__)

# out_trade_no format: ``TOPUP{YYYYMMDD}{8 hex chars}`` → 21 chars total
# (well within Alipay's 64-char ``out_trade_no`` ceiling).
_ORDER_NO_DATE_FMT = "%Y%m%d"

# Alipay "paid" trade statuses. Everything else (WAIT_BUYER_PAY, TRADE_CLOSED,
# etc.) means "don't credit yet".
_TRADE_STATUS_PAID = frozenset({"TRADE_SUCCESS", "TRADE_FINISHED"})
_TRADE_STATUS_CLOSED = "TRADE_CLOSED"


class CreateOrderResponse(TypedDict):
    """Payload returned from ``PaymentService.create_order``.

    Exactly one of ``qr_code`` / ``pay_url`` is populated depending on which
    channel handled the request; the other is ``None``.
    """

    order_id: str
    out_trade_no: str
    provider: str
    amount_fen: int
    qr_code: str | None
    pay_url: str | None
    expires_at: str  # ISO 8601 (naive UTC)


class PaymentService:
    """Topup order lifecycle (create / notify / query / close)."""

    def __init__(
        self,
        *,
        qr_provider: PaymentProvider,
        page_provider: PaymentProvider,
        qr_max_fen: int,
        min_amount_fen: int,
        max_amount_fen: int,
        order_timeout_min: int,
        enabled: bool,
        expected_app_id: str,
        alerter: PaymentAlerter | None = None,
        large_amount_threshold_fen: int = 0,
    ) -> None:
        self._qr = qr_provider
        self._page = page_provider
        self._qr_max_fen = qr_max_fen
        self._min_amount_fen = min_amount_fen
        self._max_amount_fen = max_amount_fen
        self._order_timeout_min = order_timeout_min
        self._enabled = enabled
        self._expected_app_id = expected_app_id
        self._alerter: PaymentAlerter = alerter if alerter is not None else LoggingPaymentAlerter()
        self._large_amount_threshold_fen = large_amount_threshold_fen

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls) -> PaymentService:
        """Build the default PaymentService from ``dify_config``."""
        client = AlipayClient.from_config(dify_config)
        return cls(
            qr_provider=AlipayQrProvider(client),
            page_provider=AlipayPageProvider(client),
            qr_max_fen=dify_config.ALIPAY_QR_MAX_FEN,
            min_amount_fen=dify_config.ALIPAY_MIN_AMOUNT_FEN,
            max_amount_fen=dify_config.ALIPAY_PAGE_MAX_FEN,
            order_timeout_min=dify_config.ALIPAY_ORDER_TIMEOUT_MIN,
            enabled=dify_config.ALIPAY_ENABLED,
            expected_app_id=str(dify_config.ALIPAY_APP_ID or ""),
            alerter=LoggingPaymentAlerter(),
            large_amount_threshold_fen=dify_config.ALIPAY_LARGE_AMOUNT_THRESHOLD,
        )

    # ------------------------------------------------------------------
    # Order creation
    # ------------------------------------------------------------------

    def create_order(
        self,
        *,
        tenant_id: str,
        account_id: str,
        amount_fen: int,
        subject: str = "钱包充值",
        client_ip: str | None = None,
    ) -> CreateOrderResponse:
        """Create a pending PaymentOrder and request the upstream QR / pay_url.

        The role check (owner-only) is the controller's responsibility — this
        method only validates amount + config and routes the call.

        Raises
        ------
        PaymentDisabled
            Topup is globally disabled (``ALIPAY_ENABLED=false``).
        AmountTooSmall / AmountTooLarge
            Amount falls outside the configured per-transaction bounds.
        ProviderBusinessError
            The upstream Alipay call failed. The local order is marked
            ``FAILED`` before this re-raises.
        """
        if not self._enabled:
            raise PaymentDisabled("Alipay topup is disabled (ALIPAY_ENABLED=false)")
        if amount_fen < self._min_amount_fen:
            raise AmountTooSmall(amount_fen=amount_fen, min_fen=self._min_amount_fen)
        if amount_fen > self._max_amount_fen:
            raise AmountTooLarge(amount_fen=amount_fen, max_fen=self._max_amount_fen)

        provider = self._route(amount_fen)
        out_trade_no = self._generate_order_no()
        expires_at = naive_utc_now().replace(microsecond=0) + timedelta(minutes=self._order_timeout_min)
        amount = Decimal(amount_fen) / Decimal(100)

        order = PaymentOrder(
            provider=provider.name,
            out_trade_no=out_trade_no,
            tenant_id=tenant_id,
            account_id=account_id,
            amount=amount,
            amount_fen=amount_fen,
            subject=subject,
            status=PaymentOrderStatus.PENDING.value,
            expires_at=expires_at,
            client_ip=client_ip,
        )
        db.session.add(order)
        db.session.commit()

        # Call upstream; on business failure mark FAILED locally and re-raise.
        try:
            result = provider.create_order(
                out_trade_no=out_trade_no,
                amount_fen=amount_fen,
                subject=subject,
                timeout_express=f"{self._order_timeout_min}m",
                client_ip=client_ip,
            )
        except ProviderBusinessError:
            order.status = PaymentOrderStatus.FAILED.value
            db.session.add(order)
            db.session.commit()
            logger.warning(
                "Upstream create_order failed out_trade_no=%s provider=%s",
                out_trade_no,
                provider.name,
            )
            raise

        order.qr_code = result["qr_code"]
        order.prepay_raw = result["raw"]
        db.session.add(order)
        db.session.commit()

        logger.info(
            "Created topup order out_trade_no=%s tenant=%s amount_fen=%d provider=%s",
            out_trade_no,
            tenant_id,
            amount_fen,
            provider.name,
        )

        # Fire-and-forget alert for large topups. Threshold <=0 means disabled.
        # Any alerter failure must not break order creation.
        threshold = self._large_amount_threshold_fen
        if threshold > 0 and amount_fen >= threshold:
            try:
                self._alerter.alert_large_amount(order, threshold)
            except Exception:
                logger.exception(
                    "PaymentAlerter raised; ignoring out_trade_no=%s", out_trade_no
                )

        return CreateOrderResponse(
            order_id=order.id,
            out_trade_no=out_trade_no,
            provider=provider.name,
            amount_fen=amount_fen,
            qr_code=result["qr_code"],
            pay_url=result["pay_url"],
            expires_at=expires_at.isoformat(),
        )

    # ------------------------------------------------------------------
    # Async notify
    # ------------------------------------------------------------------

    def handle_notify(self, params: dict[str, str]) -> bool:
        """Validate an Alipay async notification and credit the workspace.

        Returns ``True`` when the caller should respond ``"success"`` to
        Alipay. Idempotent: replayed notifies for an already-PAID order
        return ``True`` without re-crediting. Returns ``False`` on signature
        failure, missing order, or amount / app_id mismatch — the caller
        should respond ``"fail"`` so Alipay retries.
        """
        out_trade_no = params.get("out_trade_no")
        if not out_trade_no:
            logger.warning("Notify missing out_trade_no")
            return False

        # Row-lock the order so concurrent replays from Alipay serialize
        # behind us — the second one sees status=PAID and short-circuits.
        order = db.session.scalar(
            select(PaymentOrder)
            .where(PaymentOrder.out_trade_no == out_trade_no)
            .with_for_update()
        )
        if order is None:
            logger.warning("Notify for unknown order out_trade_no=%s", out_trade_no)
            return False

        provider = self._provider_for(order.provider)
        if not provider.verify_notify(params):
            logger.warning("Notify signature failed out_trade_no=%s", out_trade_no)
            return False

        # Defence-in-depth: even if signature verified against our key, refuse
        # a cross-account notify. Catches config drift or replayed payloads
        # signed by a rotated-in app.
        if params.get("app_id") != self._expected_app_id:
            logger.warning(
                "Notify app_id mismatch out_trade_no=%s got=%s expected=%s",
                out_trade_no,
                params.get("app_id"),
                self._expected_app_id,
            )
            return False

        # Idempotency: already credited. Return True so Alipay stops retrying.
        if order.status == PaymentOrderStatus.PAID.value:
            logger.info("Notify replay for already-paid order out_trade_no=%s", out_trade_no)
            return True

        trade_status = params.get("trade_status")
        if trade_status not in _TRADE_STATUS_PAID:
            # TRADE_CLOSED → mark local order CLOSED so the frontend stops
            # polling. Anything else (WAIT_BUYER_PAY, etc.) is a no-op ACK.
            if trade_status == _TRADE_STATUS_CLOSED:
                order.status = PaymentOrderStatus.CLOSED.value
                order.notify_raw = json.dumps(params, ensure_ascii=False)
                db.session.add(order)
                db.session.commit()
            return True

        # Amount cross-check — belt-and-braces against tampered payloads that
        # somehow survived signature verification (shouldn't happen, but the
        # cost of getting this wrong is paying out real money).
        notify_total = params.get("total_amount")
        expected = (Decimal(order.amount_fen) / Decimal(100)).quantize(Decimal("0.01"))
        if not self._amounts_match(notify_total, expected):
            logger.error(
                "Notify amount mismatch out_trade_no=%s expected=%s got=%s",
                out_trade_no,
                expected,
                notify_total,
            )
            return False

        # Credit the workspace atomically with the order / billing updates.
        order.status = PaymentOrderStatus.PAID.value
        order.provider_trade_no = params.get("trade_no")
        order.paid_at = naive_utc_now()
        order.notify_raw = json.dumps(params, ensure_ascii=False)
        db.session.add(order)

        TenantBalanceService.topup(tenant_id=order.tenant_id, amount=order.amount)

        record = BillingRecord(
            account_id=order.account_id,
            tenant_id=order.tenant_id,
            amount=order.amount,
            record_type=BillingRecordType.TOPUP.value,
            scope="tenant",
            description=f"Alipay topup {out_trade_no}",
        )
        db.session.add(record)
        db.session.commit()

        logger.info(
            "Credited topup out_trade_no=%s tenant=%s amount=%s",
            out_trade_no,
            order.tenant_id,
            str(order.amount),
        )
        return True

    # ------------------------------------------------------------------
    # Order operations
    # ------------------------------------------------------------------

    def get_order(self, *, tenant_id: str, out_trade_no: str) -> PaymentOrder:
        """Fetch a topup order scoped to a tenant.

        Raises
        ------
        OrderNotFound
            No matching order for this tenant / out_trade_no pair — also
            raised for cross-tenant lookups so attackers can't probe order
            existence.
        """
        order = db.session.scalar(
            select(PaymentOrder).where(
                PaymentOrder.out_trade_no == out_trade_no,
                PaymentOrder.tenant_id == tenant_id,
            )
        )
        if order is None:
            raise OrderNotFound(out_trade_no=out_trade_no)
        return order

    def list_tenant_orders(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PaymentOrder], int]:
        """Return a page of orders for a workspace (newest first) with total."""
        base = select(PaymentOrder).where(PaymentOrder.tenant_id == tenant_id)
        total = db.session.scalar(select(db.func.count()).select_from(base.subquery())) or 0
        rows = list(
            db.session.scalars(
                base.order_by(PaymentOrder.created_at.desc()).limit(limit).offset(offset)
            ).all()
        )
        return rows, total

    def close_order(self, *, tenant_id: str, out_trade_no: str) -> PaymentOrder:
        """Close a pending order locally and upstream.

        Upstream-close business errors (e.g. ``ACQ.TRADE_NOT_EXIST`` when the
        order was never confirmed at Alipay) are logged but do not prevent
        the local close — the end state is identical.

        Raises
        ------
        OrderNotFound
            No such order for this tenant.
        OrderAlreadyClosed
            Order is not in the PENDING state.
        """
        order = self.get_order(tenant_id=tenant_id, out_trade_no=out_trade_no)
        if order.status != PaymentOrderStatus.PENDING.value:
            raise OrderAlreadyClosed(status=order.status)

        provider = self._provider_for(order.provider)
        try:
            provider.close_order(out_trade_no)
        except ProviderBusinessError as e:
            logger.info(
                "Upstream close returned business error (non-fatal) out_trade_no=%s %s",
                out_trade_no,
                e,
            )

        order.status = PaymentOrderStatus.CLOSED.value
        db.session.add(order)
        db.session.commit()
        return order

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _route(self, amount_fen: int) -> PaymentProvider:
        """Select a provider based on amount.

        ``amount_fen <= ALIPAY_QR_MAX_FEN`` → QR (当面付 precreate).
        Otherwise → Page (电脑网站支付 page.pay).
        """
        return self._qr if amount_fen <= self._qr_max_fen else self._page

    def _provider_for(self, provider_name: str) -> PaymentProvider:
        """Look up the provider instance by the name stored on the order."""
        if provider_name == PaymentProviderName.ALIPAY_QR.value:
            return self._qr
        return self._page

    @staticmethod
    def _amounts_match(notify_total: str | None, expected: Decimal) -> bool:
        """Compare Alipay's ``total_amount`` string against our expected value.

        Safely handles missing / malformed values without raising.
        """
        if notify_total is None:
            return False
        try:
            return Decimal(notify_total) == expected
        except (ArithmeticError, ValueError):
            return False

    @staticmethod
    def _generate_order_no() -> str:
        """Generate a 21-char ``TOPUP{YYYYMMDD}{hex8}`` order number."""
        today = naive_utc_now().strftime(_ORDER_NO_DATE_FMT)
        return f"TOPUP{today}{secrets.token_hex(4).upper()}"
