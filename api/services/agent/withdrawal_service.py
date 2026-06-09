"""WithdrawalService — agent-initiated payouts, sysadmin-marked-paid.

Lifecycle: pending → paid / rejected.

Wallet is NOT decremented at request creation; only ``mark_paid`` moves
money. This keeps the request a pure intent record so a rejected payout
doesn't have to refund anything.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, select

from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.agent import (
    AgentWallet,
    PayoutMethod,
    WithdrawalRequest,
    WithdrawalStatus,
)
from services.errors.agent import (
    DuplicatePendingWithdrawalError,
    InsufficientWithdrawableBalanceError,
    WithdrawalAmountTooSmallError,
    WithdrawalRequestNotFoundError,
)

MIN_WITHDRAWAL = Decimal(100)
_VALID_METHODS = frozenset(m.value for m in PayoutMethod)


class WithdrawalService:
    """Manage withdrawal requests + sysadmin payouts."""

    @classmethod
    def create_request(
        cls, *,
        agent_id: str,
        amount: Decimal,
        payout_method: str,
        payout_payload: dict,
    ) -> WithdrawalRequest:
        """Stage a pending request. Caller commits."""
        if amount < MIN_WITHDRAWAL:
            raise WithdrawalAmountTooSmallError(
                f"min withdrawal is {MIN_WITHDRAWAL}"
            )
        if payout_method not in _VALID_METHODS:
            raise ValueError(f"unknown payout method {payout_method!r}")

        existing = db.session.scalar(
            select(WithdrawalRequest).where(
                and_(
                    WithdrawalRequest.agent_id == agent_id,
                    WithdrawalRequest.status == WithdrawalStatus.PENDING.value,
                )
            )
        )
        if existing:
            raise DuplicatePendingWithdrawalError(
                f"agent {agent_id} already has a pending withdrawal"
            )

        wallet = db.session.scalar(
            select(AgentWallet).where(AgentWallet.agent_id == agent_id)
        )
        if wallet is None or wallet.withdrawable < amount:
            available = wallet.withdrawable if wallet is not None else Decimal(0)
            raise InsufficientWithdrawableBalanceError(
                f"available {available} < requested {amount}"
            )

        req = WithdrawalRequest(
            agent_id=agent_id,
            amount=amount,
            payout_method=payout_method,
            payout_payload=payout_payload,
        )
        db.session.add(req)
        return req

    @classmethod
    def mark_paid(
        cls, request_id: str, *,
        reviewer_id: str, transaction_id: str,
    ) -> WithdrawalRequest:
        """Sysadmin marks the request paid. Atomically decrements the wallet
        in the same session. Caller commits."""
        req = db.session.scalar(
            select(WithdrawalRequest).where(WithdrawalRequest.id == request_id)
        )
        if req is None or req.status != WithdrawalStatus.PENDING.value:
            raise WithdrawalRequestNotFoundError(
                f"withdrawal {request_id} not pending"
            )

        wallet = db.session.scalar(
            select(AgentWallet).where(AgentWallet.agent_id == req.agent_id)
        )
        if wallet is None or wallet.withdrawable < req.amount:
            raise InsufficientWithdrawableBalanceError(
                "wallet balance changed since request — aborting payout"
            )

        wallet.withdrawable = wallet.withdrawable - req.amount
        wallet.total_withdrawn = wallet.total_withdrawn + req.amount

        req.status = WithdrawalStatus.PAID.value
        req.reviewer_id = reviewer_id
        req.review_note = transaction_id
        req.reviewed_at = naive_utc_now()
        return req

    @classmethod
    def reject(
        cls, request_id: str, *,
        reviewer_id: str, note: Optional[str] = None,
    ) -> WithdrawalRequest:
        req = db.session.scalar(
            select(WithdrawalRequest).where(WithdrawalRequest.id == request_id)
        )
        if req is None or req.status != WithdrawalStatus.PENDING.value:
            raise WithdrawalRequestNotFoundError(
                f"withdrawal {request_id} not pending"
            )
        req.status = WithdrawalStatus.REJECTED.value
        req.reviewer_id = reviewer_id
        req.review_note = note
        req.reviewed_at = naive_utc_now()
        return req
