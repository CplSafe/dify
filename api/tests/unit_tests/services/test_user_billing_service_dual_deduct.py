"""Test dual deduction (Tenant + User) for workflow runs.

The refactored ``deduct_for_workflow_run`` must decrement BOTH
``UserBalance.balance`` AND ``TenantBalance.locked`` atomically, and must
write two ``BillingRecord`` rows (``scope="user"`` and ``scope="tenant"``).

Both wallets are permitted to go negative - a deliberate product choice so
workflows already in flight are not killed mid-run when a user is low on
credits.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from models.creator import BillingRecord, BillingRecordType, TenantBalance, UserBalance
from services.user_billing_service import UserBillingService


def _make_tenant_balance(*, locked: Decimal = Decimal(0), balance: Decimal = Decimal(0)) -> TenantBalance:
    tb = TenantBalance(tenant_id="t1")
    tb.locked = locked
    tb.balance = balance
    return tb


def _make_user_balance(*, balance: Decimal = Decimal(0)) -> UserBalance:
    ub = UserBalance(account_id="a1")
    ub.balance = balance
    return ub


def _added_billing_records(mock_db) -> list[BillingRecord]:
    """Collect every BillingRecord added via either ``db.session.add`` or
    ``db.session.add_all`` on the mocked session."""
    records: list[BillingRecord] = []
    for call in mock_db.session.add.call_args_list:
        obj = call.args[0]
        if isinstance(obj, BillingRecord):
            records.append(obj)
    for call in mock_db.session.add_all.call_args_list:
        objs = call.args[0]
        for obj in objs:
            if isinstance(obj, BillingRecord):
                records.append(obj)
    return records


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_deduct_decrements_both_wallets(mock_db, mock_tb_svc):
    # Arrange
    tb = _make_tenant_balance(locked=Decimal(100))
    ub = _make_user_balance(balance=Decimal(100))
    mock_tb_svc.get_or_create.return_value = tb

    # Act
    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        UserBillingService.deduct_for_workflow_run(
            account_id="a1",
            tenant_id="t1",
            workflow_run_id="w1",
            total_tokens=1000,
            price_per_1k_tokens=Decimal("0.5"),
        )

    # Assert
    assert ub.balance == Decimal("99.500000")
    assert tb.locked == Decimal("99.500000")
    records = _added_billing_records(mock_db)
    assert len(records) == 2


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_deduct_writes_both_scope_records(mock_db, mock_tb_svc):
    # Arrange
    tb = _make_tenant_balance(locked=Decimal(100))
    ub = _make_user_balance(balance=Decimal(100))
    mock_tb_svc.get_or_create.return_value = tb

    # Act
    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        UserBillingService.deduct_for_workflow_run(
            account_id="a1",
            tenant_id="t1",
            workflow_run_id="w1",
            total_tokens=2000,
            price_per_1k_tokens=Decimal("0.1"),
        )

    # Assert
    records = _added_billing_records(mock_db)
    type_scope_pairs = {(r.record_type, r.scope) for r in records}
    assert (BillingRecordType.DEDUCTION.value, "user") in type_scope_pairs
    assert (BillingRecordType.DEDUCTION.value, "tenant") in type_scope_pairs


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_deduct_zero_tokens_returns_none_and_no_mutation(mock_db, mock_tb_svc):
    # Arrange
    tb = _make_tenant_balance(locked=Decimal(100))
    ub = _make_user_balance(balance=Decimal(100))
    mock_tb_svc.get_or_create.return_value = tb

    # Act
    with patch.object(UserBillingService, "get_or_create_balance", return_value=ub) as mock_get_ub:
        result = UserBillingService.deduct_for_workflow_run(
            account_id="a1",
            tenant_id="t1",
            workflow_run_id="w1",
            total_tokens=0,
            price_per_1k_tokens=Decimal("0.5"),
        )

    # Assert
    assert result is None
    assert ub.balance == Decimal(100)
    assert tb.locked == Decimal(100)
    mock_get_ub.assert_not_called()
    mock_tb_svc.get_or_create.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_deduct_allows_negative_balance(mock_db, mock_tb_svc):
    """Starting at zero on both wallets, deduction still succeeds and both
    balances become negative. Deliberate product choice: workflows in flight
    are not blocked mid-run."""
    # Arrange
    tb = _make_tenant_balance(locked=Decimal(0))
    ub = _make_user_balance(balance=Decimal(0))
    mock_tb_svc.get_or_create.return_value = tb

    # Act
    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        result = UserBillingService.deduct_for_workflow_run(
            account_id="a1",
            tenant_id="t1",
            workflow_run_id="w1",
            total_tokens=1000,
            price_per_1k_tokens=Decimal("0.5"),
        )

    # Assert
    assert result is not None
    assert ub.balance == Decimal("-0.500000")
    assert tb.locked == Decimal("-0.500000")


# ---------------------------------------------------------------------------
# check_can_run: pre-flight gate before starting a workflow run
# ---------------------------------------------------------------------------


@patch("services.user_billing_service.TenantBalanceService")
def test_check_can_run_allows_when_both_positive(mock_tb_svc):
    tb = _make_tenant_balance(locked=Decimal(10))
    ub = _make_user_balance(balance=Decimal(5))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        ok, code = UserBillingService.check_can_run("a1", "t1")

    assert ok is True
    assert code is None


@patch("services.user_billing_service.TenantBalanceService")
def test_check_can_run_blocks_when_user_zero(mock_tb_svc):
    tb = _make_tenant_balance(locked=Decimal(10))
    ub = _make_user_balance(balance=Decimal(0))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        ok, code = UserBillingService.check_can_run("a1", "t1")

    assert ok is False
    assert code == "INSUFFICIENT_USER_BUDGET"


@patch("services.user_billing_service.TenantBalanceService")
def test_check_can_run_blocks_when_user_negative(mock_tb_svc):
    tb = _make_tenant_balance(locked=Decimal(10))
    ub = _make_user_balance(balance=Decimal("-0.1"))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        ok, code = UserBillingService.check_can_run("a1", "t1")

    assert ok is False
    assert code == "INSUFFICIENT_USER_BUDGET"


@patch("services.user_billing_service.TenantBalanceService")
def test_check_can_run_blocks_when_tenant_pool_drained(mock_tb_svc):
    """User has credit on paper but tenant.locked <= 0 means the pool is exhausted.
    Running would drive the invariant deeper into the red; block early."""
    tb = _make_tenant_balance(locked=Decimal(0))
    ub = _make_user_balance(balance=Decimal(5))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        ok, code = UserBillingService.check_can_run("a1", "t1")

    assert ok is False
    assert code == "INSUFFICIENT_TENANT_BUDGET"


def test_check_balance_positive_backwards_compat_delegates_to_check_can_run():
    """Existing callers that pass only account_id still work, by assuming
    the user's balance is the binding check."""
    ub = _make_user_balance(balance=Decimal(5))
    with patch.object(UserBillingService, "get_or_create_balance", return_value=ub):
        assert UserBillingService.check_balance_positive("a1") is True

    ub_zero = _make_user_balance(balance=Decimal(0))
    with patch.object(UserBillingService, "get_or_create_balance", return_value=ub_zero):
        assert UserBillingService.check_balance_positive("a1") is False


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_deduct_returns_user_record(mock_db, mock_tb_svc):
    """Caller relies on the returned record being the user-scope one."""
    # Arrange
    tb = _make_tenant_balance(locked=Decimal(100))
    ub = _make_user_balance(balance=Decimal(100))
    mock_tb_svc.get_or_create.return_value = tb

    # Act
    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        record = UserBillingService.deduct_for_workflow_run(
            account_id="a1",
            tenant_id="t1",
            workflow_run_id="w1",
            total_tokens=1000,
            price_per_1k_tokens=Decimal("0.5"),
        )

    # Assert
    assert record is not None
    assert record.scope == "user"
    assert record.record_type == BillingRecordType.DEDUCTION.value
    assert record.account_id == "a1"
    assert record.tenant_id == "t1"
    assert record.workflow_run_id == "w1"


# ---------------------------------------------------------------------------
# assert_can_run: exception-driven wrapper used by the workflow entry gate
# ---------------------------------------------------------------------------


@patch("services.user_billing_service.TenantBalanceService")
def test_assert_can_run_returns_silently_when_allowed(mock_tb_svc):
    """Happy path: no exception, no return value."""
    tb = _make_tenant_balance(locked=Decimal(10))
    ub = _make_user_balance(balance=Decimal(5))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        # Should not raise.
        UserBillingService.assert_can_run("a1", "t1")


@patch("services.user_billing_service.TenantBalanceService")
def test_assert_can_run_raises_with_user_budget_code(mock_tb_svc):
    from services.wallet.exceptions import WorkflowBudgetExceeded

    tb = _make_tenant_balance(locked=Decimal(10))
    ub = _make_user_balance(balance=Decimal(0))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        with pytest.raises(WorkflowBudgetExceeded) as exc:
            UserBillingService.assert_can_run("a1", "t1")
    assert exc.value.code == "INSUFFICIENT_USER_BUDGET"


@patch("services.user_billing_service.TenantBalanceService")
def test_assert_can_run_raises_with_tenant_budget_code(mock_tb_svc):
    from services.wallet.exceptions import WorkflowBudgetExceeded

    tb = _make_tenant_balance(locked=Decimal(0))
    ub = _make_user_balance(balance=Decimal(5))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance", return_value=ub),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
    ):
        with pytest.raises(WorkflowBudgetExceeded) as exc:
            UserBillingService.assert_can_run("a1", "t1")
    assert exc.value.code == "INSUFFICIENT_TENANT_BUDGET"


# ---------------------------------------------------------------------------
# Owner branch — Solution 2: owners draw from TenantBalance.balance directly
# and never hold a per-member UserBalance pool.
# ---------------------------------------------------------------------------


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_deduct_for_owner_decrements_tenant_balance_only(mock_db, mock_tb_svc):
    """Owner path: TenantBalance.balance -= cost; TenantBalance.locked and
    UserBalance are NOT touched. UserBillingService.get_or_create_balance must
    not be called at all (owners don't hold a UserBalance pool)."""
    tb = _make_tenant_balance(balance=Decimal(100), locked=Decimal(50))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance") as mock_get_ub,
        patch.object(UserBillingService, "is_tenant_owner", return_value=True),
    ):
        record = UserBillingService.deduct_for_workflow_run(
            account_id="owner1",
            tenant_id="t1",
            workflow_run_id="w1",
            total_tokens=1000,
            price_per_1k_tokens=Decimal("0.5"),
        )

    assert tb.balance == Decimal("99.500000")
    assert tb.locked == Decimal(50)  # unchanged
    mock_get_ub.assert_not_called()
    assert record is not None
    assert record.scope == "tenant"
    assert record.record_type == BillingRecordType.DEDUCTION.value


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_deduct_for_owner_writes_single_tenant_scope_record(mock_db, mock_tb_svc):
    """Owner deduction emits exactly one BillingRecord with scope='tenant'."""
    tb = _make_tenant_balance(balance=Decimal(100), locked=Decimal(0))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance"),
        patch.object(UserBillingService, "is_tenant_owner", return_value=True),
    ):
        UserBillingService.deduct_for_workflow_run(
            account_id="owner1",
            tenant_id="t1",
            workflow_run_id="w1",
            total_tokens=2000,
            price_per_1k_tokens=Decimal("0.1"),
        )

    records = _added_billing_records(mock_db)
    assert len(records) == 1
    assert records[0].scope == "tenant"
    assert records[0].record_type == BillingRecordType.DEDUCTION.value


@patch("services.user_billing_service.TenantBalanceService")
def test_check_can_run_owner_allows_when_tenant_balance_positive(mock_tb_svc):
    """Owner gating is a single check on TenantBalance.balance > 0.
    UserBalance is irrelevant because the owner never has one."""
    tb = _make_tenant_balance(balance=Decimal(10), locked=Decimal(0))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance") as mock_get_ub,
        patch.object(UserBillingService, "is_tenant_owner", return_value=True),
    ):
        ok, code = UserBillingService.check_can_run("owner1", "t1")

    assert ok is True
    assert code is None
    mock_get_ub.assert_not_called()


@patch("services.user_billing_service.TenantBalanceService")
def test_check_can_run_owner_blocks_when_tenant_balance_zero(mock_tb_svc):
    """Owner gate: TenantBalance.balance == 0 blocks the run with the tenant
    code (no user code is ever emitted for owners)."""
    tb = _make_tenant_balance(balance=Decimal(0), locked=Decimal(0))
    mock_tb_svc.get_or_create.return_value = tb

    with (
        patch.object(UserBillingService, "get_or_create_balance"),
        patch.object(UserBillingService, "is_tenant_owner", return_value=True),
    ):
        ok, code = UserBillingService.check_can_run("owner1", "t1")

    assert ok is False
    assert code == "INSUFFICIENT_TENANT_BUDGET"
