"""Unit tests for UserBillingService.get_or_create_balance.

Mirrors the guarantees we enforce on TenantBalanceService.get_or_create:
the first-ever creation must NOT commit — the caller owns the transaction
boundary. A nested commit on the topup path could persist
``PaymentOrder.status=paid`` before the rest of the wallet write lands,
breaking atomicity if the outer commit later fails.
"""
from decimal import Decimal
from unittest.mock import patch

from services.user_billing_service import UserBillingService


@patch("services.user_billing_service.db")
def test_get_or_create_balance_creates_when_missing_without_commit(mock_db):
    """When no row exists, INSERT ... ON CONFLICT DO NOTHING, then re-read.

    Must NOT commit — the caller (e.g. an allocation flow) bundles this
    write with other mutations into a single atomic commit.
    """
    from models.creator import UserBalance

    created = UserBalance(account_id="a-1")
    # First scalar() → None (no row); second scalar() after insert → created row.
    mock_db.session.scalar.side_effect = [None, created]

    result = UserBillingService.get_or_create_balance("a-1")

    assert result is created
    # Insert must be issued via db.session.execute (pg insert) — not
    # via db.session.add + commit.
    mock_db.session.execute.assert_called_once()
    mock_db.session.commit.assert_not_called()


@patch("services.user_billing_service.db")
def test_get_or_create_balance_returns_existing_without_commit(mock_db):
    """When a row already exists, return it without insert/commit."""
    from models.creator import UserBalance

    existing = UserBalance(account_id="a-1")
    existing.balance = Decimal(50)
    mock_db.session.scalar.return_value = existing

    result = UserBillingService.get_or_create_balance("a-1")

    assert result is existing
    assert result.balance == Decimal(50)
    mock_db.session.add.assert_not_called()
    mock_db.session.execute.assert_not_called()
    mock_db.session.commit.assert_not_called()
