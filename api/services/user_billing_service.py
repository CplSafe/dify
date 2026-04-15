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
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models import Account, TenantAccountJoin, TenantAccountRole
from models.creator import BillingRecord, BillingRecordType, TenantBalance, UserBalance
from models.engine import db
from services.wallet.tenant_balance_service import TenantBalanceService


@dataclass(frozen=True)
class AdminBalanceRow:
    """Denormalised super-admin balance row.

    One row per account (not per wallet), so newly-created owners — who
    have an ``accounts`` row and a ``TenantAccountJoin`` but no
    ``UserBalance`` yet — still show up. ``role`` reflects the account's
    role in its *current* tenant; owners read ``TenantBalance.balance``,
    members read ``UserBalance.balance``. When the authoritative wallet
    row is missing we report 0 so operators see the account instead of
    having it silently disappear.
    """

    account_id: str
    account_name: str
    account_email: str
    role: str | None  # "owner" | "admin" | "normal" | None (no tenant yet)
    tenant_id: str | None
    balance: Decimal
    currency: str
    is_sufficient: bool
    updated_at: datetime | None


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
    def is_tenant_owner(cls, account_id: str, tenant_id: str) -> bool:
        """Return True when the account is the owner of the tenant.

        Used by ``check_can_run`` and ``deduct_for_workflow_run`` to route
        the owner down the single-wallet path (``TenantBalance.balance``
        only) instead of the dual-deduct path. Allocation rules also key
        off this — the owner's funds are workspace funds, so allocating
        "to the owner" is a no-op that would break the invariant.
        """
        role = db.session.scalar(
            select(TenantAccountJoin.role).where(
                TenantAccountJoin.tenant_id == tenant_id,
                TenantAccountJoin.account_id == account_id,
            )
        )
        return role == TenantAccountRole.OWNER.value

    @classmethod
    def check_balance_positive(cls, account_id: str) -> bool:
        """Return True if the user's personal ``UserBalance`` is positive.

        WARNING: user-balance-only. Does NOT consider the owner's
        ``TenantBalance.balance`` (single-wallet path) or the workspace
        pool (``TenantBalance.locked``). Using this on the marketplace path
        falsely blocks owners who hold all their funds on the tenant wallet.

        Prefer ``check_can_run(account_id, tenant_id)`` anywhere the tenant
        is known — it handles owner vs member correctly and returns the
        differentiated error code callers need for user-facing messages.
        """
        balance = cls.get_or_create_balance(account_id)
        return balance.is_sufficient()

    @classmethod
    def check_can_run(cls, account_id: str, tenant_id: str) -> tuple[bool, str | None]:
        """Pre-flight check before starting a workflow run.

        Returns ``(can_run, error_code)``. ``error_code`` is ``None`` when the
        run may proceed, otherwise one of:

        - ``"INSUFFICIENT_USER_BUDGET"`` — the member's personal balance is
          not positive (member path only).
        - ``"INSUFFICIENT_OWNER_BUDGET"`` — the owner's spendable
          ``TenantBalance.balance`` is exhausted (owner path only). Surfaces
          a different HTTP error so the UI can prompt the owner to top up
          instead of telling them to "ask the owner".
        - ``"INSUFFICIENT_TENANT_BUDGET"`` — the workspace's allocated pool
          (``TenantBalance.locked``) is drained. Member-only signal: it
          means there's nothing left to bill against even if the member's
          personal wallet still looks positive.

        Owner path (single wallet): owners spend workspace funds directly
        from ``TenantBalance.balance``. They don't hold a ``UserBalance``,
        so the user-budget check is skipped.

        Member path (dual wallet): member must have personal budget AND
        the allocated pool (``locked``) must still be positive — a drained
        pool blocks every member even if their personal balance looks
        positive on paper (it would drive the invariant deeper into red).

        All checks are strict (> 0) because ``deduct_for_workflow_run`` is
        allowed to push wallets negative mid-run. Blocking here prevents
        starting *new* runs once a pool is empty.
        """
        tenant_balance = TenantBalanceService.get_or_create(tenant_id)

        if cls.is_tenant_owner(account_id, tenant_id):
            if tenant_balance.balance <= Decimal(0):
                return False, "INSUFFICIENT_OWNER_BUDGET"
            return True, None

        user_balance = cls.get_or_create_balance(account_id)
        if not user_balance.is_sufficient():
            return False, "INSUFFICIENT_USER_BUDGET"

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
        """Deduct cost of a workflow run from the caller's effective wallet.

        Two branches:

        - **Owner** (single-wallet): decrement ``TenantBalance.balance``.
          Owners spend workspace funds directly; they don't hold a
          ``UserBalance``. Only one ``BillingRecord`` is written
          (``scope="tenant"``).
        - **Member** (dual-wallet): decrement BOTH ``UserBalance.balance``
          AND ``TenantBalance.locked`` by the same amount, atomically,
          and write two ``BillingRecord`` rows (``scope="user"`` and
          ``scope="tenant"``) for independent ledger views.

        Returns the primary record (tenant-scope for owner, user-scope for
        member), or ``None`` if ``total_tokens`` is zero or the computed
        amount rounds to zero.

        Balances are permitted to go negative: this is a deliberate
        product choice so workflows already in flight are not killed
        mid-run when a wallet just crosses zero.
        """
        if total_tokens <= 0:
            return None

        amount = (Decimal(total_tokens) / Decimal(1000)) * price_per_1k_tokens
        amount = amount.quantize(Decimal("0.000001"))

        if amount <= Decimal(0):
            return None

        description = f"Workflow run {workflow_run_id}: {total_tokens} tokens"

        if cls.is_tenant_owner(account_id, tenant_id):
            # Owner path: single-wallet deduction against TenantBalance.balance.
            # No UserBalance is touched — the owner does not hold one.
            tenant_balance = TenantBalanceService.get_or_create(tenant_id, for_update=True)
            tenant_balance.balance -= amount
            db.session.add(tenant_balance)

            if tenant_balance.balance < Decimal(0):
                logger.warning(
                    "Tenant balance went negative after owner workflow deduction "
                    "tenant=%s balance=%s",
                    tenant_id,
                    str(tenant_balance.balance),
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
            db.session.add(tenant_record)
            db.session.commit()

            logger.info(
                "Billed owner account=%s tenant=%s workflow=%s tokens=%d amount=%s",
                account_id,
                tenant_id,
                workflow_run_id,
                total_tokens,
                str(amount),
            )
            return tenant_record

        # Member path: dual-wallet deduction.
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
    def list_admin_account_balances(
        cls, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[AdminBalanceRow], int]:
        """Enumerate accounts with their authoritative balance for the super admin view.

        Driven by ``accounts`` (one row per user), LEFT JOIN the current
        tenant/role + both wallet tables. The old ``SELECT * FROM user_balances``
        implementation missed every freshly-registered owner because
        ``UserBalance`` is only created for members — owners live on
        ``TenantBalance``. Keying off ``accounts`` makes the view
        account-complete instead of wallet-complete.

        Ordering by ``Account.created_at DESC`` surfaces newly-registered
        users first, which matches the operator's mental model when
        investigating a just-signed-up report.
        """
        # Total count is "every account", paginated below. We deliberately do
        # NOT filter out BANNED/CLOSED accounts here — operators need to see
        # them to debug billing disputes. UI can filter client-side if desired.
        total = db.session.scalar(
            select(func.count()).select_from(Account)
        ) or 0

        # Pick the account's "current" tenant/role (one current row per
        # account by convention) so the balance shown matches which wallet
        # they actually draw from. Accounts with no current tenant yet
        # (mid-registration, edge state) fall through to role=NULL.
        current_join = (
            select(
                TenantAccountJoin.account_id,
                TenantAccountJoin.tenant_id,
                TenantAccountJoin.role,
            )
            .where(TenantAccountJoin.current.is_(True))
            .subquery()
        )

        # LEFT JOIN both wallet tables so a missing row renders as 0 instead
        # of dropping the account. The CASE in the SELECT picks the
        # authoritative wallet based on role.
        rows = db.session.execute(
            select(
                Account.id,
                Account.name,
                Account.email,
                current_join.c.tenant_id,
                current_join.c.role,
                UserBalance.balance,
                UserBalance.currency,
                UserBalance.updated_at,
                TenantBalance.balance,
                TenantBalance.currency,
                TenantBalance.updated_at,
            )
            .select_from(Account)
            .join(current_join, current_join.c.account_id == Account.id, isouter=True)
            .join(UserBalance, UserBalance.account_id == Account.id, isouter=True)
            .join(TenantBalance, TenantBalance.tenant_id == current_join.c.tenant_id, isouter=True)
            .order_by(Account.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        result: list[AdminBalanceRow] = []
        for (
            acc_id, acc_name, acc_email,
            tenant_id, role,
            ub_balance, ub_currency, ub_updated,
            tb_balance, tb_currency, tb_updated,
        ) in rows:
            is_owner = role == TenantAccountRole.OWNER.value
            if is_owner:
                balance = tb_balance if tb_balance is not None else Decimal(0)
                currency = tb_currency or "CNY"
                updated_at = tb_updated
            else:
                balance = ub_balance if ub_balance is not None else Decimal(0)
                currency = ub_currency or "CNY"
                updated_at = ub_updated

            result.append(
                AdminBalanceRow(
                    account_id=acc_id,
                    account_name=acc_name or "",
                    account_email=acc_email or "",
                    role=role,
                    tenant_id=tenant_id,
                    balance=balance,
                    currency=currency,
                    is_sufficient=balance > Decimal(0),
                    updated_at=updated_at,
                )
            )
        return result, total


def generate_api_key() -> str:
    """Generate a secure random user global API key."""
    return USER_API_KEY_PREFIX + secrets.token_urlsafe(32)
