"""Unit tests for TenantBalanceService."""
from decimal import Decimal
from unittest.mock import patch

import pytest

from services.wallet.tenant_balance_service import TenantBalanceService


@patch("services.wallet.tenant_balance_service.db")
def test_get_or_create_creates_when_missing(mock_db):
    """When no row exists, create one with zero balance and commit."""
    mock_db.session.scalar.return_value = None

    result = TenantBalanceService.get_or_create("t-1")

    assert result.tenant_id == "t-1"
    assert result.balance == Decimal(0)
    assert result.locked == Decimal(0)
    assert result.total_topup == Decimal(0)
    mock_db.session.add.assert_called_once()
    mock_db.session.commit.assert_called_once()


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
