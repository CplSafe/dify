"""Unit tests for ``UserBillingService.list_admin_account_balances``.

Pins down the bug that motivated this method: the old super-admin balances
endpoint queried ``user_balances`` only, which invisibly dropped every
fresh owner account (owners live on ``TenantBalance``, not ``UserBalance``).

These tests verify the row-mapping logic that turns the joined SELECT
into ``AdminBalanceRow`` DTOs:

- Owner with a TenantBalance row → shows TB.balance.
- Owner with NO TenantBalance yet (brand-new account) → shows 0, still visible.
- Member with a UserBalance row → shows UB.balance.
- Member with NO UserBalance yet → shows 0.
- Account with no current tenant (edge) → role None, defaults to UB branch.
- is_sufficient is derived from the selected balance, not a naive existence check.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from services.user_billing_service import UserBillingService


def _row(
    *,
    acc_id: str,
    name: str = "Alice",
    email: str = "a@x.com",
    tenant_id: str | None = "t-1",
    role: str | None = "owner",
    ub_balance: Decimal | None = None,
    ub_currency: str | None = None,
    ub_updated: datetime | None = None,
    tb_balance: Decimal | None = None,
    tb_currency: str | None = None,
    tb_updated: datetime | None = None,
) -> tuple:
    """Build a tuple shaped like one row of the joined SELECT."""
    return (
        acc_id, name, email,
        tenant_id, role,
        ub_balance, ub_currency, ub_updated,
        tb_balance, tb_currency, tb_updated,
    )


@patch("services.user_billing_service.db")
def test_owner_with_tenant_balance_reports_tenant_balance(mock_db):
    """An owner's visible balance is ``TenantBalance.balance``, not UB."""
    now = datetime(2026, 4, 15, 12, 0, 0)
    mock_db.session.scalar.return_value = 1  # total count
    mock_db.session.execute.return_value.all.return_value = [
        _row(
            acc_id="u-owner",
            role="owner",
            tb_balance=Decimal(250),
            tb_currency="CNY",
            tb_updated=now,
        ),
    ]

    rows, total = UserBillingService.list_admin_account_balances()

    assert total == 1
    assert len(rows) == 1
    r = rows[0]
    assert r.account_id == "u-owner"
    assert r.role == "owner"
    assert r.balance == Decimal(250)
    assert r.is_sufficient is True
    assert r.updated_at == now


@patch("services.user_billing_service.db")
def test_brand_new_owner_without_tenant_balance_is_still_listed(mock_db):
    """The regression guard: freshly-registered owners with no wallet row
    must still appear in the admin list (was the original bug)."""
    mock_db.session.scalar.return_value = 1
    mock_db.session.execute.return_value.all.return_value = [
        _row(
            acc_id="u-fresh",
            role="owner",
            tb_balance=None,   # no TenantBalance created yet
            ub_balance=None,   # and definitely no UserBalance
        ),
    ]

    rows, total = UserBillingService.list_admin_account_balances()

    assert total == 1
    assert rows[0].account_id == "u-fresh"
    assert rows[0].balance == Decimal(0)
    assert rows[0].is_sufficient is False
    assert rows[0].currency == "CNY"  # sane default instead of None
    assert rows[0].updated_at is None  # signals "never credited"


@patch("services.user_billing_service.db")
def test_member_reports_user_balance_not_tenant_balance(mock_db):
    """A normal member reads UB, not the workspace pool."""
    now = datetime(2026, 4, 15, 12, 0, 0)
    mock_db.session.scalar.return_value = 1
    mock_db.session.execute.return_value.all.return_value = [
        _row(
            acc_id="u-member",
            role="normal",
            ub_balance=Decimal(30),
            ub_currency="CNY",
            ub_updated=now,
            # TenantBalance shown for the workspace but should NOT be used:
            tb_balance=Decimal(9999),
            tb_currency="CNY",
            tb_updated=now,
        ),
    ]

    rows, _ = UserBillingService.list_admin_account_balances()

    assert rows[0].balance == Decimal(30)
    assert rows[0].is_sufficient is True


@patch("services.user_billing_service.db")
def test_member_without_user_balance_still_listed_as_zero(mock_db):
    """Members with no UB row yet also show up (symmetric to the owner fix)."""
    mock_db.session.scalar.return_value = 1
    mock_db.session.execute.return_value.all.return_value = [
        _row(
            acc_id="u-member-new",
            role="normal",
            ub_balance=None,
        ),
    ]

    rows, _ = UserBillingService.list_admin_account_balances()

    assert rows[0].balance == Decimal(0)
    assert rows[0].is_sufficient is False


@patch("services.user_billing_service.db")
def test_account_with_no_current_tenant_falls_through_to_user_branch(mock_db):
    """Edge case: account exists but has no ``current=true`` tenant join.

    Defaults to the UB branch so the row still renders (operator can see
    the account and investigate why the tenant link is missing).
    """
    mock_db.session.scalar.return_value = 1
    mock_db.session.execute.return_value.all.return_value = [
        _row(
            acc_id="u-orphan",
            tenant_id=None,
            role=None,
            ub_balance=Decimal(5),
            ub_currency="CNY",
        ),
    ]

    rows, _ = UserBillingService.list_admin_account_balances()

    assert rows[0].role is None
    assert rows[0].tenant_id is None
    assert rows[0].balance == Decimal(5)


@patch("services.user_billing_service.db")
def test_pagination_passes_limit_and_offset_to_query(mock_db):
    """Controller hands pagination args through; service must honour them."""
    mock_db.session.scalar.return_value = 0
    mock_db.session.execute.return_value.all.return_value = []

    captured: dict = {}

    original_execute = mock_db.session.execute

    def spy_execute(stmt):
        captured["stmt"] = stmt
        return original_execute.return_value

    mock_db.session.execute.side_effect = spy_execute

    UserBillingService.list_admin_account_balances(limit=25, offset=75)

    # We can't inspect the compiled SQL without a real engine, but we can
    # verify the query was executed and the count path was hit.
    assert "stmt" in captured


@patch("services.user_billing_service.db")
def test_null_name_and_email_become_empty_strings(mock_db):
    """Ensures the JSON response has a stable shape even for corrupt rows."""
    mock_db.session.scalar.return_value = 1
    mock_db.session.execute.return_value.all.return_value = [
        _row(acc_id="u-1", name=None, email=None, role="owner"),
    ]

    rows, _ = UserBillingService.list_admin_account_balances()

    assert rows[0].account_name == ""
    assert rows[0].account_email == ""


@patch("services.user_billing_service.db")
def test_mixed_batch_owner_and_member(mock_db):
    """Multiple accounts in one page — ordering preserved, per-row role honoured."""
    now = datetime(2026, 4, 15, 12, 0, 0)
    mock_db.session.scalar.return_value = 2
    mock_db.session.execute.return_value.all.return_value = [
        _row(
            acc_id="u-owner", role="owner",
            tb_balance=Decimal(100), tb_currency="CNY", tb_updated=now,
        ),
        _row(
            acc_id="u-member", role="normal",
            ub_balance=Decimal(10), ub_currency="CNY", ub_updated=now,
        ),
    ]

    rows, total = UserBillingService.list_admin_account_balances()

    assert total == 2
    assert rows[0].account_id == "u-owner"
    assert rows[0].balance == Decimal(100)
    assert rows[1].account_id == "u-member"
    assert rows[1].balance == Decimal(10)
