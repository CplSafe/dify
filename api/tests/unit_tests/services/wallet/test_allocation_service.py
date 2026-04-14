"""Unit tests for AllocationService.

These tests exercise the in-session mutation logic without touching a real
database. The `db` session, `TenantBalanceService`, `UserBillingService`,
and the `_verify_tenant_member` helper are all patched so the service
under test sees controlled inputs and we can assert on the mutations it
performs.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from services.wallet.allocation_service import AllocationService
from services.wallet.exceptions import (
    InsufficientMemberBalance,
    InsufficientTenantBalance,
    NotTenantMember,
)


def _make_tenant_balance(balance: Decimal, locked: Decimal):
    from models.creator import TenantBalance

    tb = TenantBalance(tenant_id="t1")
    tb.balance = balance
    tb.locked = locked
    return tb


def _make_user_balance(balance: Decimal):
    from models.creator import UserBalance

    ub = UserBalance(account_id="a1")
    ub.balance = balance
    return ub


@patch("services.wallet.allocation_service._verify_tenant_member")
@patch("services.wallet.allocation_service.UserBillingService")
@patch("services.wallet.allocation_service.TenantBalanceService")
@patch("services.wallet.allocation_service.db")
def test_allocate_decreases_tenant_balance_and_increases_user(
    mock_db, mock_tb_svc, mock_ub_svc, mock_verify
):
    """Positive amount: tenant.balance -=, tenant.locked +=, user.balance +=."""
    tenant_balance = _make_tenant_balance(Decimal(100), Decimal(0))
    user_balance = _make_user_balance(Decimal(0))
    mock_tb_svc.get_or_create.return_value = tenant_balance
    mock_ub_svc.get_or_create_balance.return_value = user_balance

    record = AllocationService.allocate(
        tenant_id="t1",
        account_id="a1",
        operator_id="op",
        amount=Decimal(30),
    )

    assert tenant_balance.balance == Decimal(70)
    assert tenant_balance.locked == Decimal(30)
    assert user_balance.balance == Decimal(30)
    # Signed amount preserved in audit record
    assert record.amount == Decimal(30)
    mock_verify.assert_called_once_with("t1", "a1")
    mock_db.session.commit.assert_called_once()


@patch("services.wallet.allocation_service._verify_tenant_member")
@patch("services.wallet.allocation_service.UserBillingService")
@patch("services.wallet.allocation_service.TenantBalanceService")
@patch("services.wallet.allocation_service.db")
def test_reclaim_moves_funds_back_to_tenant(
    mock_db, mock_tb_svc, mock_ub_svc, mock_verify
):
    """Negative amount: tenant.balance +=, tenant.locked -=, user.balance -=."""
    tenant_balance = _make_tenant_balance(Decimal(50), Decimal(80))
    user_balance = _make_user_balance(Decimal(80))
    mock_tb_svc.get_or_create.return_value = tenant_balance
    mock_ub_svc.get_or_create_balance.return_value = user_balance

    record = AllocationService.allocate(
        tenant_id="t1",
        account_id="a1",
        operator_id="op",
        amount=Decimal(-20),
    )

    assert tenant_balance.balance == Decimal(70)
    assert tenant_balance.locked == Decimal(60)
    assert user_balance.balance == Decimal(60)
    # Signed amount preserved in audit record (negative for reclaim)
    assert record.amount == Decimal(-20)
    mock_db.session.commit.assert_called_once()


@patch("services.wallet.allocation_service._verify_tenant_member")
@patch("services.wallet.allocation_service.UserBillingService")
@patch("services.wallet.allocation_service.TenantBalanceService")
@patch("services.wallet.allocation_service.db")
def test_allocate_rejects_when_insufficient_tenant_balance(
    mock_db, mock_tb_svc, mock_ub_svc, mock_verify
):
    """Over-allocation raises before any mutation or commit."""
    tenant_balance = _make_tenant_balance(Decimal(10), Decimal(0))
    mock_tb_svc.get_or_create.return_value = tenant_balance
    mock_ub_svc.get_or_create_balance.return_value = _make_user_balance(Decimal(0))

    with pytest.raises(InsufficientTenantBalance):
        AllocationService.allocate(
            tenant_id="t1",
            account_id="a1",
            operator_id="op",
            amount=Decimal(50),
        )

    # No mutation applied, no commit issued
    assert tenant_balance.balance == Decimal(10)
    assert tenant_balance.locked == Decimal(0)
    mock_db.session.commit.assert_not_called()


@patch("services.wallet.allocation_service._verify_tenant_member")
@patch("services.wallet.allocation_service.UserBillingService")
@patch("services.wallet.allocation_service.TenantBalanceService")
@patch("services.wallet.allocation_service.db")
def test_reclaim_rejects_when_member_insufficient(
    mock_db, mock_tb_svc, mock_ub_svc, mock_verify
):
    """Reclaim larger than member balance raises before any mutation."""
    tenant_balance = _make_tenant_balance(Decimal(0), Decimal(10))
    user_balance = _make_user_balance(Decimal(10))
    mock_tb_svc.get_or_create.return_value = tenant_balance
    mock_ub_svc.get_or_create_balance.return_value = user_balance

    with pytest.raises(InsufficientMemberBalance):
        AllocationService.allocate(
            tenant_id="t1",
            account_id="a1",
            operator_id="op",
            amount=Decimal(-50),
        )

    assert tenant_balance.balance == Decimal(0)
    assert tenant_balance.locked == Decimal(10)
    assert user_balance.balance == Decimal(10)
    mock_db.session.commit.assert_not_called()


def test_allocate_zero_amount_raises_value_error():
    """amount == 0 is a caller bug; reject before touching anything."""
    with pytest.raises(ValueError):
        AllocationService.allocate(
            tenant_id="t1",
            account_id="a1",
            operator_id="op",
            amount=Decimal(0),
        )


@patch("services.wallet.allocation_service.db")
def test_allocate_raises_not_tenant_member_when_join_missing(mock_db):
    """When no TenantAccountJoin exists, NotTenantMember is raised."""
    # `db.session.scalar` returns None -> _verify_tenant_member raises
    mock_db.session.scalar.return_value = None

    with pytest.raises(NotTenantMember):
        AllocationService.allocate(
            tenant_id="t1",
            account_id="a1",
            operator_id="op",
            amount=Decimal(10),
        )


@patch("services.wallet.allocation_service._verify_tenant_member")
@patch("services.wallet.allocation_service.UserBillingService")
@patch("services.wallet.allocation_service.TenantBalanceService")
@patch("services.wallet.allocation_service.db")
def test_allocate_writes_allocation_and_billing_records(
    mock_db, mock_tb_svc, mock_ub_svc, mock_verify
):
    """A successful allocate persists both AllocationRecord and BillingRecord."""
    from models.creator import AllocationRecord, BillingRecord, BillingRecordType

    tenant_balance = _make_tenant_balance(Decimal(100), Decimal(0))
    user_balance = _make_user_balance(Decimal(0))
    mock_tb_svc.get_or_create.return_value = tenant_balance
    mock_ub_svc.get_or_create_balance.return_value = user_balance

    AllocationService.allocate(
        tenant_id="t1",
        account_id="a1",
        operator_id="op",
        amount=Decimal(25),
        description="Q2 budget",
    )

    mock_db.session.add_all.assert_called_once()
    added = mock_db.session.add_all.call_args.args[0]
    assert len(added) == 2

    allocation = next(r for r in added if isinstance(r, AllocationRecord))
    billing = next(r for r in added if isinstance(r, BillingRecord))

    assert allocation.tenant_id == "t1"
    assert allocation.account_id == "a1"
    assert allocation.operator_id == "op"
    assert allocation.amount == Decimal(25)
    assert allocation.description == "Q2 budget"

    assert billing.tenant_id == "t1"
    assert billing.account_id == "a1"
    assert billing.amount == Decimal(25)
    assert billing.record_type == BillingRecordType.ALLOCATION.value
    assert billing.scope == "user"


@patch("services.wallet.allocation_service._verify_tenant_member")
@patch("services.wallet.allocation_service.UserBillingService")
@patch("services.wallet.allocation_service.TenantBalanceService")
@patch("services.wallet.allocation_service.db")
def test_reclaim_records_preserve_signed_amount(
    mock_db, mock_tb_svc, mock_ub_svc, mock_verify
):
    """Reclaim writes negative amount on both AllocationRecord and BillingRecord."""
    from models.creator import AllocationRecord, BillingRecord

    tenant_balance = _make_tenant_balance(Decimal(0), Decimal(40))
    user_balance = _make_user_balance(Decimal(40))
    mock_tb_svc.get_or_create.return_value = tenant_balance
    mock_ub_svc.get_or_create_balance.return_value = user_balance

    AllocationService.allocate(
        tenant_id="t1",
        account_id="a1",
        operator_id="op",
        amount=Decimal(-15),
    )

    added = mock_db.session.add_all.call_args.args[0]
    allocation = next(r for r in added if isinstance(r, AllocationRecord))
    billing = next(r for r in added if isinstance(r, BillingRecord))

    assert allocation.amount == Decimal(-15)
    assert billing.amount == Decimal(-15)
