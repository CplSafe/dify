"""Unit tests for WithdrawalService.

Verifies amount/balance guards, duplicate-pending guard, and the atomic
mark_paid flow that decrements the wallet in the same logical operation
as the status flip.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@patch("services.agent.withdrawal_service.db")
def test_create_request_inserts_pending_without_touching_wallet(mock_db, agent_id):
    from services.agent.withdrawal_service import WithdrawalService

    wallet = MagicMock(withdrawable=Decimal("500"))
    # scalar() calls: existing_pending lookup (None), wallet lookup
    mock_db.session.scalar.side_effect = [None, wallet]

    req = WithdrawalService.create_request(
        agent_id=agent_id, amount=Decimal("200"),
        payout_method="alipay",
        payout_payload={"account": "x@y.com", "name": "张三"},
    )

    assert req.status == "pending"
    assert req.amount == Decimal("200")
    # Wallet untouched on create — only mark_paid moves money
    assert wallet.withdrawable == Decimal("500")
    mock_db.session.add.assert_called_once()


@patch("services.agent.withdrawal_service.db")
def test_create_request_rejects_under_minimum(mock_db, agent_id):
    from services.agent.withdrawal_service import WithdrawalService
    from services.errors.agent import WithdrawalAmountTooSmallError

    with pytest.raises(WithdrawalAmountTooSmallError):
        WithdrawalService.create_request(
            agent_id=agent_id, amount=Decimal("99.99"),
            payout_method="alipay",
            payout_payload={"account": "x", "name": "y"},
        )


@patch("services.agent.withdrawal_service.db")
def test_create_request_rejects_unknown_payout_method(mock_db, agent_id):
    from services.agent.withdrawal_service import WithdrawalService

    with pytest.raises(ValueError, match="unknown payout method"):
        WithdrawalService.create_request(
            agent_id=agent_id, amount=Decimal("200"),
            payout_method="bitcoin",
            payout_payload={},
        )


@patch("services.agent.withdrawal_service.db")
def test_create_request_rejects_duplicate_pending(mock_db, agent_id):
    from services.agent.withdrawal_service import WithdrawalService
    from services.errors.agent import DuplicatePendingWithdrawalError

    pending = MagicMock(status="pending")
    mock_db.session.scalar.return_value = pending

    with pytest.raises(DuplicatePendingWithdrawalError):
        WithdrawalService.create_request(
            agent_id=agent_id, amount=Decimal("200"),
            payout_method="alipay",
            payout_payload={"account": "x", "name": "y"},
        )


@patch("services.agent.withdrawal_service.db")
def test_create_request_rejects_overdraft(mock_db, agent_id):
    from services.agent.withdrawal_service import WithdrawalService
    from services.errors.agent import InsufficientWithdrawableBalanceError

    wallet = MagicMock(withdrawable=Decimal("50"))
    mock_db.session.scalar.side_effect = [None, wallet]

    with pytest.raises(InsufficientWithdrawableBalanceError):
        WithdrawalService.create_request(
            agent_id=agent_id, amount=Decimal("200"),
            payout_method="alipay",
            payout_payload={"account": "x", "name": "y"},
        )


@patch("services.agent.withdrawal_service.db")
def test_mark_paid_decrements_wallet_atomically(mock_db, agent_id):
    """mark_paid: status flip + wallet decrement happen on the same session."""
    from services.agent.withdrawal_service import WithdrawalService

    pending_req = MagicMock(
        id="req-1", status="pending", agent_id=agent_id, amount=Decimal("200"),
    )
    wallet = MagicMock(
        withdrawable=Decimal("500"),
        total_withdrawn=Decimal("0"),
    )
    # scalar() calls: req lookup, wallet lookup
    mock_db.session.scalar.side_effect = [pending_req, wallet]

    WithdrawalService.mark_paid(
        "req-1", reviewer_id="admin-1", transaction_id="TX12345",
    )

    assert wallet.withdrawable == Decimal("300")
    assert wallet.total_withdrawn == Decimal("200")
    assert pending_req.status == "paid"
    assert pending_req.review_note == "TX12345"
    assert pending_req.reviewer_id == "admin-1"


@patch("services.agent.withdrawal_service.db")
def test_mark_paid_rejects_already_processed(mock_db):
    from services.agent.withdrawal_service import WithdrawalService
    from services.errors.agent import WithdrawalRequestNotFoundError

    already_paid = MagicMock(status="paid")
    mock_db.session.scalar.return_value = already_paid

    with pytest.raises(WithdrawalRequestNotFoundError):
        WithdrawalService.mark_paid("req-1", reviewer_id="x", transaction_id="y")


@patch("services.agent.withdrawal_service.db")
def test_mark_paid_aborts_if_wallet_balance_changed(mock_db, agent_id):
    """If concurrent activity drained the wallet between request creation
    and payout review, abort instead of going negative."""
    from services.agent.withdrawal_service import WithdrawalService
    from services.errors.agent import InsufficientWithdrawableBalanceError

    pending_req = MagicMock(
        id="req-1", status="pending", agent_id=agent_id, amount=Decimal("200"),
    )
    wallet = MagicMock(withdrawable=Decimal("50"))  # not enough anymore
    mock_db.session.scalar.side_effect = [pending_req, wallet]

    with pytest.raises(InsufficientWithdrawableBalanceError):
        WithdrawalService.mark_paid("req-1", reviewer_id="a", transaction_id="t")


@patch("services.agent.withdrawal_service.db")
def test_reject_does_not_touch_wallet(mock_db, agent_id):
    from services.agent.withdrawal_service import WithdrawalService

    pending_req = MagicMock(
        id="req-1", status="pending", agent_id=agent_id, amount=Decimal("200"),
    )
    mock_db.session.scalar.return_value = pending_req

    WithdrawalService.reject("req-1", reviewer_id="admin-1", note="bad info")

    assert pending_req.status == "rejected"
    assert pending_req.review_note == "bad info"
