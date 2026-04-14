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

from models.creator import BillingRecord, BillingRecordType, UserBalance
from models.engine import db
from services.wallet.tenant_balance_service import TenantBalanceService

logger = logging.getLogger(__name__)

# Prefix for user global API keys
USER_API_KEY_PREFIX = "ugak-"


class UserBillingService:
    """Service for user-level balance and billing operations."""

    @classmethod
    def get_or_create_balance(cls, account_id: str) -> UserBalance:
        """Return existing balance row or create one with zero balance."""
        balance = db.session.scalar(select(UserBalance).where(UserBalance.account_id == account_id))
        if balance is None:
            balance = UserBalance(account_id=account_id)
            db.session.add(balance)
            db.session.commit()
        return balance

    @classmethod
    def get_balance(cls, account_id: str) -> UserBalance:
        return cls.get_or_create_balance(account_id)

    @classmethod
    def check_balance_positive(cls, account_id: str) -> bool:
        """Return True if balance > 0."""
        balance = cls.get_or_create_balance(account_id)
        return balance.is_sufficient()

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

        user_balance = cls.get_or_create_balance(account_id)
        tenant_balance = TenantBalanceService.get_or_create(tenant_id)

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

        balance = cls.get_or_create_balance(account_id)
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
