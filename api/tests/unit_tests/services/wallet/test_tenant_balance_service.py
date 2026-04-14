"""Unit tests for TenantBalanceService."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.wallet.tenant_balance_service import TenantBalanceService


@patch("services.wallet.tenant_balance_service.db")
def test_get_or_create_creates_when_missing(mock_db):
    """When no row exists, INSERT ... ON CONFLICT DO NOTHING, then re-read.

    Must NOT commit — the caller owns the transaction boundary. A nested
    commit during a topup (notify handler) could persist
    ``PaymentOrder.status=paid`` before the wallet increment, breaking
    atomicity if the outer commit later fails.
    """
    from models.creator import TenantBalance

    created = TenantBalance(tenant_id="t-1")
    # First scalar() → None (no row); second scalar() after insert → created row.
    mock_db.session.scalar.side_effect = [None, created]

    result = TenantBalanceService.get_or_create("t-1")

    assert result is created
    # Must have issued an INSERT via db.session.execute (pg insert) — not
    # via a bare db.session.add + commit.
    mock_db.session.execute.assert_called_once()
    mock_db.session.commit.assert_not_called()


@patch("services.wallet.tenant_balance_service.db")
def test_get_or_create_returns_existing(mock_db):
    """When a row exists, return it without insert/commit."""
    from models.creator import TenantBalance

    existing = TenantBalance(tenant_id="t-1")
    existing.balance = Decimal(100)
    mock_db.session.scalar.return_value = existing

    result = TenantBalanceService.get_or_create("t-1")

    assert result.balance == Decimal(100)
    mock_db.session.add.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("services.wallet.tenant_balance_service.db")
def test_get_returns_none_when_missing(mock_db):
    """get() returns None when no row exists (no side effects)."""
    mock_db.session.scalar.return_value = None

    result = TenantBalanceService.get("t-missing")

    assert result is None
    mock_db.session.add.assert_not_called()
    mock_db.session.commit.assert_not_called()


@patch("services.wallet.tenant_balance_service.db")
def test_has_funds_true_when_balance_positive(mock_db):
    from models.creator import TenantBalance

    tb = TenantBalance(tenant_id="t1")
    tb.balance = Decimal(5)
    tb.locked = Decimal(0)
    mock_db.session.scalar.return_value = tb

    assert TenantBalanceService.has_funds("t1") is True


@patch("services.wallet.tenant_balance_service.db")
def test_has_funds_true_when_only_locked_positive(mock_db):
    from models.creator import TenantBalance

    tb = TenantBalance(tenant_id="t1")
    tb.balance = Decimal(0)
    tb.locked = Decimal(3)
    mock_db.session.scalar.return_value = tb

    assert TenantBalanceService.has_funds("t1") is True


@patch("services.wallet.tenant_balance_service.db")
def test_has_funds_false_when_both_zero(mock_db):
    from models.creator import TenantBalance

    tb = TenantBalance(tenant_id="t1")
    tb.balance = Decimal(0)
    tb.locked = Decimal(0)
    mock_db.session.scalar.return_value = tb

    assert TenantBalanceService.has_funds("t1") is False


@patch("services.wallet.tenant_balance_service.db")
def test_has_funds_false_when_row_missing(mock_db):
    mock_db.session.scalar.return_value = None

    assert TenantBalanceService.has_funds("t-missing") is False


# ---------------------------------------------------------------------------
# topup
# ---------------------------------------------------------------------------


@patch("services.wallet.tenant_balance_service.db")
def test_topup_adds_to_balance_and_total_topup(mock_db):
    """Positive amount credits both spendable balance and audit total_topup."""
    # Arrange
    from models.creator import TenantBalance

    existing = TenantBalance(tenant_id="t-1")
    existing.balance = Decimal(10)
    existing.total_topup = Decimal(5)
    mock_db.session.scalar.return_value = existing

    # Act
    result = TenantBalanceService.topup(tenant_id="t-1", amount=Decimal("20.00"))

    # Assert
    assert result.balance == Decimal("30.00")
    assert result.total_topup == Decimal("25.00")
    # topup itself must NOT commit — caller owns the transaction boundary.
    mock_db.session.commit.assert_not_called()
    mock_db.session.add.assert_called_with(existing)


@patch("services.wallet.tenant_balance_service.db")
def test_topup_rejects_zero_amount(mock_db):
    """Zero amount is rejected — only strictly positive credits allowed."""
    with pytest.raises(ValueError, match="must be positive"):
        TenantBalanceService.topup(tenant_id="t-1", amount=Decimal(0))


@patch("services.wallet.tenant_balance_service.db")
def test_topup_rejects_negative_amount(mock_db):
    """Negative amounts are rejected — use AllocationService for reclaim."""
    with pytest.raises(ValueError, match="must be positive"):
        TenantBalanceService.topup(tenant_id="t-1", amount=Decimal(-5))


@patch("services.wallet.tenant_balance_service.db")
def test_topup_on_first_ever_call_does_not_commit(mock_db):
    """First-ever topup for a tenant (no TenantBalance row yet) must still
    leave the transaction open — the outer notify handler bundles the wallet
    credit with PaymentOrder + BillingRecord writes in a single commit.
    """
    from models.creator import TenantBalance

    created = TenantBalance(tenant_id="t-new")
    created.balance = Decimal(0)
    created.total_topup = Decimal(0)
    # First scalar() returns None → get_or_create goes down the insert branch;
    # second returns the just-inserted row.
    mock_db.session.scalar.side_effect = [None, created]

    result = TenantBalanceService.topup(tenant_id="t-new", amount=Decimal("12.00"))

    assert result.balance == Decimal("12.00")
    assert result.total_topup == Decimal("12.00")
    mock_db.session.commit.assert_not_called()


@patch("services.wallet.tenant_balance_service.db")
def test_topup_accumulates_across_calls(mock_db):
    """Multiple topups compound both balance and total_topup correctly."""
    # Arrange
    from models.creator import TenantBalance

    existing = TenantBalance(tenant_id="t-1")
    existing.balance = Decimal(0)
    existing.total_topup = Decimal(0)
    mock_db.session.scalar.return_value = existing

    # Act
    TenantBalanceService.topup(tenant_id="t-1", amount=Decimal(100))
    TenantBalanceService.topup(tenant_id="t-1", amount=Decimal(50))

    # Assert
    assert existing.balance == Decimal(150)
    assert existing.total_topup == Decimal(150)


# ---------------------------------------------------------------------------
# for_update: row-level locking for money-path callers
# ---------------------------------------------------------------------------


@patch("services.wallet.tenant_balance_service.select")
@patch("services.wallet.tenant_balance_service.db")
def test_get_or_create_for_update_locks_the_row(mock_db, mock_select):
    """``for_update=True`` must build a SELECT ... FOR UPDATE statement.

    Concurrent allocate / deduct / topup calls must serialise on the row
    or the balance invariants break (read → mutate → commit without a
    lock leaves the winner's write visible to the loser's stale snapshot).
    """
    from models.creator import TenantBalance

    existing = TenantBalance(tenant_id="t-1")
    mock_db.session.scalar.return_value = existing

    where_stmt = MagicMock(name="where_stmt")
    locked_stmt = MagicMock(name="locked_stmt")
    where_stmt.with_for_update.return_value = locked_stmt
    mock_select.return_value.where.return_value = where_stmt

    result = TenantBalanceService.get_or_create("t-1", for_update=True)

    assert result is existing
    where_stmt.with_for_update.assert_called_once()
    mock_db.session.scalar.assert_called_once_with(locked_stmt)


@patch("services.wallet.tenant_balance_service.select")
@patch("services.wallet.tenant_balance_service.db")
def test_get_or_create_default_does_not_lock(mock_db, mock_select):
    """Default (``for_update=False``) must not lock — read-only callers
    (wallet widget, billing history) hit this path and should never block
    on concurrent writers."""
    from models.creator import TenantBalance

    existing = TenantBalance(tenant_id="t-1")
    mock_db.session.scalar.return_value = existing

    where_stmt = MagicMock(name="where_stmt")
    mock_select.return_value.where.return_value = where_stmt

    TenantBalanceService.get_or_create("t-1")

    where_stmt.with_for_update.assert_not_called()
