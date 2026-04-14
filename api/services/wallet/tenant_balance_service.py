"""Tenant-level wallet operations.

The TenantBalance row holds three money pools for a workspace:
- `balance`: unallocated funds the owner can assign to members
- `locked`: funds already allocated to members (sum of UserBalance.balance)
- `total_topup`: running total of money paid in (audit/reporting only)

Invariant (enforced by AllocationService): Σ(UserBalance.balance for members
of tenant) == TenantBalance.locked. This service handles plain read/write;
atomic transfers live in AllocationService.
"""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.creator import TenantBalance
from models.engine import db

logger = logging.getLogger(__name__)


class TenantBalanceService:
    """Read/write operations on TenantBalance."""

    @classmethod
    def get_or_create(cls, tenant_id: str) -> TenantBalance:
        """Return the workspace's balance row, creating a zeroed one if absent.

        Uses ``INSERT ... ON CONFLICT DO NOTHING`` followed by a re-read, so
        the insert participates in the caller's transaction without committing
        it. A nested commit here would be catastrophic on the topup path:
        ``PaymentOrder.status=paid`` must land in the same transaction as the
        wallet increment, or a mid-flow failure could mark the order paid while
        the balance stays zero. The ON CONFLICT clause also makes two
        concurrent first-topup requests safe — the loser reads the winner's
        row instead of raising IntegrityError.
        """
        row = db.session.scalar(
            select(TenantBalance).where(TenantBalance.tenant_id == tenant_id)
        )
        if row is not None:
            return row

        stmt = (
            pg_insert(TenantBalance)
            .values(tenant_id=tenant_id)
            .on_conflict_do_nothing(index_elements=["tenant_id"])
        )
        db.session.execute(stmt)
        # Re-read: the row now exists (either we inserted it, or a concurrent
        # transaction did and our insert was a no-op).
        row = db.session.scalar(
            select(TenantBalance).where(TenantBalance.tenant_id == tenant_id)
        )
        if row is None:
            # Defensive: should be unreachable because of the ON CONFLICT guard.
            raise RuntimeError(f"TenantBalance for tenant_id={tenant_id} not visible after insert")
        return row

    @classmethod
    def get(cls, tenant_id: str) -> TenantBalance | None:
        """Return the balance row or None. No side effects."""
        return db.session.scalar(
            select(TenantBalance).where(TenantBalance.tenant_id == tenant_id)
        )

    @classmethod
    def has_funds(cls, tenant_id: str) -> bool:
        """True if the workspace has any money (balance or locked) on record."""
        b = cls.get(tenant_id)
        return b is not None and (b.balance > 0 or b.locked > 0)

    @classmethod
    def topup(cls, *, tenant_id: str, amount: Decimal) -> TenantBalance:
        """Credit a workspace with paid-in funds from a completed top-up.

        Increments both ``balance`` (spendable) and ``total_topup`` (audit).
        Must run inside an outer transaction — this method does NOT commit so
        callers can bundle the wallet write with PaymentOrder / BillingRecord
        updates atomically.

        Raises
        ------
        ValueError
            If ``amount`` is not strictly positive.
        """
        if amount <= Decimal(0):
            raise ValueError("Top-up amount must be positive")
        balance = cls.get_or_create(tenant_id)
        balance.balance += amount
        balance.total_topup += amount
        db.session.add(balance)
        return balance
