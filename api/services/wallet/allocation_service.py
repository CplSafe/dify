"""Allocation/reclaim operations for tenant->member fund movements.

Every allocation is a three-step transfer the service performs atomically
in a single DB transaction:

- allocate (amount > 0): tenant.balance -= N; tenant.locked += N; user.balance += N
- reclaim (amount < 0): tenant.balance += N; tenant.locked -= N; user.balance -= N

This preserves the strict budget invariant:

    Σ(UserBalance.balance for members of tenant) == TenantBalance.locked

Note on concurrency: this module performs plain in-session mutation and
commits the unit of work. Row-level locking (``SELECT ... FOR UPDATE``)
for concurrent workflow-run deductions is handled at the integration
layer in a follow-up task; callers at the HTTP boundary should serialise
allocation requests per tenant.
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

        tenant_balance = TenantBalanceService.get_or_create(tenant_id)
        user_balance = UserBillingService.get_or_create_balance(account_id)

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
