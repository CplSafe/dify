"""Allocation/reclaim operations for tenant->member fund movements.

Every allocation is a three-step transfer the service performs atomically
in a single DB transaction:

- allocate (amount > 0): tenant.balance -= N; tenant.locked += N; user.balance += N
- reclaim (amount < 0): tenant.balance += N; tenant.locked -= N; user.balance -= N

This preserves the strict budget invariant:

    Σ(UserBalance.balance for members of tenant) == TenantBalance.locked

Concurrency: every row touched (``TenantBalance``, ``UserBalance``) is
read with ``SELECT ... FOR UPDATE`` so concurrent allocate / reclaim /
topup-credit / workflow-deduct calls serialise on the physical row.
**Lock order is fixed tenant → user everywhere** (see the matching
comment in ``UserBillingService.deduct_for_workflow_run``) to avoid
circular waits.
"""

import logging
from decimal import Decimal

from sqlalchemy import select

from models import TenantAccountJoin
from models.creator import (
    AllocationRecord,
    BillingRecord,
    BillingRecordType,
)
from models.engine import db
from services.user_billing_service import UserBillingService
from services.wallet.exceptions import (
    InsufficientMemberBalance,
    InsufficientTenantBalance,
    NotTenantMember,
)
from services.wallet.tenant_balance_service import TenantBalanceService

logger = logging.getLogger(__name__)


def _verify_tenant_member(tenant_id: str, account_id: str) -> None:
    """Raise NotTenantMember if the account is not a member of the tenant."""
    join = db.session.scalar(
        select(TenantAccountJoin).where(
            TenantAccountJoin.tenant_id == tenant_id,
            TenantAccountJoin.account_id == account_id,
        )
    )
    if join is None:
        raise NotTenantMember(f"account {account_id} is not in tenant {tenant_id}")


class AllocationService:
    """Allocate workspace funds to members and reclaim them."""

    @classmethod
    def allocate(
        cls,
        *,
        tenant_id: str,
        account_id: str,
        operator_id: str,
        amount: Decimal,
        description: str | None = None,
    ) -> AllocationRecord:
        """Allocate (positive amount) or reclaim (negative amount) funds.

        Invariants enforced:
        - allocate: tenant.balance >= amount
        - reclaim: user.balance >= |amount|

        The signed ``amount`` is persisted verbatim on both the
        ``AllocationRecord`` and the ``BillingRecord`` so audit queries
        can distinguish allocations from reclaims by sign.
        """
        if amount == 0:
            raise ValueError("amount must be non-zero")

        _verify_tenant_member(tenant_id, account_id)

        # Lock order: tenant → user (see module docstring). The lock must be
        # held across the balance check below so a concurrent allocate /
        # workflow-deduct can't slip in and invalidate the `>= amount` guard.
        tenant_balance = TenantBalanceService.get_or_create(tenant_id, for_update=True)
        user_balance = UserBillingService.get_or_create_balance(account_id, for_update=True)

        if amount > 0:
            if tenant_balance.balance < amount:
                raise InsufficientTenantBalance(
                    f"tenant {tenant_id} has only {tenant_balance.balance}, "
                    f"cannot allocate {amount}"
                )
            tenant_balance.balance -= amount
            tenant_balance.locked += amount
            user_balance.balance += amount
        else:
            reclaim_amt = -amount
            if user_balance.balance < reclaim_amt:
                raise InsufficientMemberBalance(
                    f"member {account_id} has only {user_balance.balance}, "
                    f"cannot reclaim {reclaim_amt}"
                )
            tenant_balance.balance += reclaim_amt
            tenant_balance.locked -= reclaim_amt
            user_balance.balance -= reclaim_amt

        record = AllocationRecord(
            tenant_id=tenant_id,
            account_id=account_id,
            operator_id=operator_id,
            amount=amount,
            description=description,
        )
        billing = BillingRecord(
            account_id=account_id,
            amount=amount,
            record_type=BillingRecordType.ALLOCATION.value,
            tenant_id=tenant_id,
            description=description or f"Allocation by {operator_id}",
            scope="user",
        )
        db.session.add_all([record, billing])
        db.session.commit()

        logger.info(
            "Allocated tenant=%s account=%s amount=%s by=%s",
            tenant_id,
            account_id,
            amount,
            operator_id,
        )
        return record

    @classmethod
    def list_tenant_allocations(
        cls,
        *,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AllocationRecord], int]:
        """Return a page of allocation records for a workspace (newest first).

        Mirrors ``PaymentService.list_tenant_orders`` so the console audit
        view can render allocations and topups with the same pagination
        contract.
        """
        base = select(AllocationRecord).where(AllocationRecord.tenant_id == tenant_id)
        total = db.session.scalar(select(db.func.count()).select_from(base.subquery())) or 0
        rows = list(
            db.session.scalars(
                base.order_by(AllocationRecord.created_at.desc()).limit(limit).offset(offset)
            ).all()
        )
        return rows, total
