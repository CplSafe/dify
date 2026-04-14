"""User-level billing service.

Manages per-account credit balances and billing records. Separate from the
tenant-level TenantCreditPool which tracks workspace-wide quota.

Rules:
- Balance can go negative (debt). Workflows are blocked when balance <= 0.
- Deductions happen after a workflow run terminates (any terminal state).
- Top-ups are performed by super admins.
"""

import logging
import secrets
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.creator import BillingRecord, BillingRecordType, UserBalance
from models.engine import db
from services.wallet.tenant_balance_service import TenantBalanceService

logger = logging.getLogger(__name__)

# Prefix for user global API keys
USER_API_KEY_PREFIX = "ugak-"


class UserBillingService:
    """Service for user-level balance and billing operations."""

    @classmethod
    def get_or_create_balance(cls, account_id: str, *, for_update: bool = False) -> UserBalance:
        """Return the user's balance row, creating a zeroed one if absent.

        Uses ``INSERT ... ON CONFLICT DO NOTHING`` followed by a re-read so
        the insert participates in the caller's transaction without an
        implicit commit. A nested commit here would break the topup path:
        ``PaymentOrder.status=paid`` must land in the same transaction as
        the wallet write, or a mid-flow failure could mark the order paid
        while the balance stays unchanged. The ON CONFLICT clause also
        makes two concurrent first-creates safe — the loser reads the
        winner's row instead of raising IntegrityError.

        Pass ``for_update=True`` on the money path (allocate / workflow
        deduction) to take a ``SELECT ... FOR UPDATE`` row lock so
        concurrent writers serialise. Read-only callers (wallet widget,
        billing history) leave this False so they never block on writers.
        """
        stmt = select(UserBalance).where(UserBalance.account_id == account_id)
        if for_update:
            stmt = stmt.with_for_update()
        balance = db.session.scalar(stmt)
        if balance is not None:
            return balance

        insert_stmt = (
            pg_insert(UserBalance)
            .values(account_id=account_id)
            .on_conflict_do_nothing(index_elements=["account_id"])
        )
        db.session.execute(insert_stmt)
        stmt = select(UserBalance).where(UserBalance.account_id == account_id)
        if for_update:
            stmt = stmt.with_for_update()
        balance = db.session.scalar(stmt)
        if balance is None:
            # Defensive: should be unreachable because of the ON CONFLICT guard.
            raise RuntimeError(f"UserBalance for account_id={account_id} not visible after insert")
        return balance

    @classmethod
    def get_balance(cls, account_id: str) -> UserBalance:
        return cls.get_or_create_balance(account_id)

    @classmethod
    def check_balance_positive(cls, account_id: str) -> bool:
        """Return True if the user balance is positive.

        Backward-compatible gate used by callers that only know about per-user
        balance. Prefer ``check_can_run`` when the tenant is available, as it
        also guards against a drained workspace pool.
        """
        balance = cls.get_or_create_balance(account_id)
        return balance.is_sufficient()

    @classmethod
    def check_can_run(cls, account_id: str, tenant_id: str) -> tuple[bool, str | None]:
        """Pre-flight check before starting a workflow run.

        Returns ``(can_run, error_code)``. ``error_code`` is ``None`` when the
        run may proceed, otherwise one of:

        - ``"INSUFFICIENT_USER_BUDGET"`` — the member's personal balance is
          not positive.
        - ``"INSUFFICIENT_TENANT_BUDGET"`` — the workspace's allocated pool
          (``TenantBalance.locked``) is exhausted; no member can run even if
          their personal balance is still positive on paper.

        Both checks are strict (> 0) because ``deduct_for_workflow_run`` is
        allowed to push either wallet negative mid-run. Blocking here prevents
        starting *new* runs once the pool is empty.
        """
        user_balance = cls.get_or_create_balance(account_id)
        if not user_balance.is_sufficient():
            return False, "INSUFFICIENT_USER_BUDGET"

        tenant_balance = TenantBalanceService.get_or_create(tenant_id)
        if tenant_balance.locked <= Decimal(0):
            return False, "INSUFFICIENT_TENANT_BUDGET"

        return True, None

    @classmethod
    def assert_can_run(cls, account_id: str, tenant_id: str) -> None:
        """Raise ``WorkflowBudgetExceeded`` when the member cannot start a run.

        Thin wrapper over ``check_can_run`` for callers that prefer the
        exception-driven control flow (e.g. the ``AppGenerateService``
        entry point, where every other quota / rate-limit check raises).

        The raised exception's ``code`` mirrors the string returned by
        ``check_can_run`` so HTTP error mapping stays in lockstep.
        """
        # Local import: ``WorkflowBudgetExceeded`` lives in services.wallet
        # and pulling it at module top would create a wallet -> billing ->
        # wallet import cycle (TenantBalanceService is already imported here).
        from services.wallet.exceptions import WorkflowBudgetExceeded

        ok, error_code = cls.check_can_run(account_id, tenant_id)
        if ok:
            return
        assert error_code is not None  # narrow for the type checker
        raise WorkflowBudgetExceeded(
            error_code=error_code,
            message=(
                f"workflow run blocked for account={account_id} tenant={tenant_id}: "
                f"{error_code}"
            ),
        )

    @classmethod
    def deduct_for_workflow_run(
        cls,
        *,
        account_id: str,
        tenant_id: str,
        workflow_run_id: str,
        total_tokens: int,
        price_per_1k_tokens: Decimal,
    ) -> BillingRecord | None:
        """Dual-deduct cost of a workflow run from both tenant and user wallets.

        Decrements ``TenantBalance.locked`` and ``UserBalance.balance`` by the
        same amount in a single commit, and writes two ``BillingRecord`` rows
        (``scope="user"`` and ``scope="tenant"``) for independent ledger views.

        Returns the user-scope ``BillingRecord``, or ``None`` if ``total_tokens``
        is zero or the computed amount rounds to zero.

        Both balances are permitted to go negative: this is a deliberate product
        choice so that workflows already in flight are not blocked mid-run.
        """
        if total_tokens <= 0:
            return None

        amount = (Decimal(total_tokens) / Decimal(1000)) * price_per_1k_tokens
        amount = amount.quantize(Decimal("0.000001"))

        if amount <= Decimal(0):
            return None

        # Lock both rows before mutating — concurrent workflow completions
        # for the same user/tenant would otherwise race each other's
        # read-modify-write and produce inconsistent locked totals.
        # Lock order is fixed **tenant → user** everywhere (matches
        # AllocationService.allocate) to prevent circular waits.
        tenant_balance = TenantBalanceService.get_or_create(tenant_id, for_update=True)
        user_balance = cls.get_or_create_balance(account_id, for_update=True)

        # Decrement both wallets. Either may go negative; we log and proceed so
        # that in-flight workflows are not killed mid-run.
        user_balance.balance -= amount
        tenant_balance.locked -= amount
        db.session.add(user_balance)
        db.session.add(tenant_balance)

        if user_balance.balance < Decimal(0):
            logger.warning(
                "User balance went negative after workflow deduction account=%s balance=%s",
                account_id,
                str(user_balance.balance),
            )
        if tenant_balance.locked < Decimal(0):
            logger.warning(
                "Tenant locked went negative after workflow deduction tenant=%s locked=%s",
                tenant_id,
                str(tenant_balance.locked),
            )

        description = f"Workflow run {workflow_run_id}: {total_tokens} tokens"
        user_record = BillingRecord(
            account_id=account_id,
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
            amount=amount,
            record_type=BillingRecordType.DEDUCTION.value,
            scope="user",
            description=description,
        )
        tenant_record = BillingRecord(
            account_id=account_id,
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
            amount=amount,
            record_type=BillingRecordType.DEDUCTION.value,
            scope="tenant",
            description=description,
        )
        db.session.add_all([user_record, tenant_record])
        db.session.commit()

        logger.info(
            "Billed account=%s tenant=%s workflow=%s tokens=%d amount=%s",
            account_id,
            tenant_id,
            workflow_run_id,
            total_tokens,
            str(amount),
        )
        return user_record

    @classmethod
    def topup(cls, *, account_id: str, amount: Decimal, description: str = "") -> BillingRecord:
        """Add credits to a user's balance. Called by super admin."""
        if amount <= Decimal(0):
            raise ValueError("Top-up amount must be positive")

        # Lock the row so concurrent topups don't race each other's read.
        balance = cls.get_or_create_balance(account_id, for_update=True)
        balance.balance += amount
        db.session.add(balance)

        record = BillingRecord(
            account_id=account_id,
            amount=amount,
            record_type=BillingRecordType.TOPUP.value,
            description=description or f"Top-up of {amount}",
        )
        db.session.add(record)
        db.session.commit()
        return record

    @classmethod
    def get_billing_records(
        cls,
        account_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BillingRecord], int]:
        """Return billing records for an account with total count."""
        base_query = select(BillingRecord).where(BillingRecord.account_id == account_id)
        total = db.session.scalar(
            select(db.func.count()).select_from(base_query.subquery())
        ) or 0
        records = list(
            db.session.scalars(
                base_query.order_by(BillingRecord.created_at.desc()).limit(limit).offset(offset)
            ).all()
        )
        return records, total

    @classmethod
    def get_all_billing_records(
        cls,
        *,
        tenant_id: str | None = None,
        account_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[BillingRecord], int]:
        """Return all billing records (for super admin). Optionally filter by tenant or account."""
        base_query = select(BillingRecord)
        if tenant_id:
            base_query = base_query.where(BillingRecord.tenant_id == tenant_id)
        if account_id:
            base_query = base_query.where(BillingRecord.account_id == account_id)
        total = db.session.scalar(
            select(db.func.count()).select_from(base_query.subquery())
        ) or 0
        records = list(
            db.session.scalars(
                base_query.order_by(BillingRecord.created_at.desc()).limit(limit).offset(offset)
            ).all()
        )
        return records, total

    @classmethod
    def get_all_balances(cls, *, limit: int = 50, offset: int = 0) -> tuple[list[UserBalance], int]:
        """Return all user balances (for super admin)."""
        base_query = select(UserBalance)
        total = db.session.scalar(
            select(db.func.count()).select_from(base_query.subquery())
        ) or 0
        balances = list(
            db.session.scalars(
                base_query.order_by(UserBalance.created_at.desc()).limit(limit).offset(offset)
            ).all()
        )
        return balances, total


def generate_api_key() -> str:
    """Generate a secure random user global API key."""
    return USER_API_KEY_PREFIX + secrets.token_urlsafe(32)
