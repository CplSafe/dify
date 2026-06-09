"""Unit tests for super-admin top-up wallet routing."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from models.creator import BillingRecord, BillingRecordType, UserBalance
from services.user_billing_service import UserBillingService


def _added_billing_records(mock_db) -> list[BillingRecord]:
    return [
        call.args[0]
        for call in mock_db.session.add.call_args_list
        if isinstance(call.args[0], BillingRecord)
    ]


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_admin_topup_owner_credits_tenant_wallet(mock_db, mock_tenant_balance_service):
    with (
        patch.object(UserBillingService, "_has_tenant_membership", return_value=True),
        patch.object(UserBillingService, "is_tenant_owner", return_value=True),
        patch.object(UserBillingService, "get_or_create_balance") as mock_get_user_balance,
    ):
        record = UserBillingService.admin_topup(
            account_id="owner-1",
            tenant_id="tenant-1",
            amount=Decimal(100),
            description="manual credit",
        )

    mock_tenant_balance_service.topup.assert_called_once_with(
        tenant_id="tenant-1",
        amount=Decimal(100),
    )
    mock_get_user_balance.assert_not_called()
    assert record.record_type == BillingRecordType.TOPUP.value
    assert record.scope == "tenant"
    assert record.tenant_id == "tenant-1"
    assert record.description == "manual credit"
    assert _added_billing_records(mock_db) == [record]
    mock_db.session.commit.assert_called_once()


@patch("services.user_billing_service.TenantBalanceService")
@patch("services.user_billing_service.db")
def test_admin_topup_member_credits_user_wallet(mock_db, mock_tenant_balance_service):
    user_balance = UserBalance(account_id="member-1")
    user_balance.balance = Decimal(20)

    with (
        patch.object(UserBillingService, "_has_tenant_membership", return_value=True),
        patch.object(UserBillingService, "is_tenant_owner", return_value=False),
        patch.object(UserBillingService, "get_or_create_balance", return_value=user_balance) as mock_get_user_balance,
    ):
        record = UserBillingService.admin_topup(
            account_id="member-1",
            tenant_id="tenant-1",
            amount=Decimal(30),
        )

    mock_tenant_balance_service.topup.assert_not_called()
    mock_get_user_balance.assert_called_once_with("member-1", for_update=True)
    assert user_balance.balance == Decimal(50)
    assert record.record_type == BillingRecordType.TOPUP.value
    assert record.scope == "user"
    assert record.tenant_id == "tenant-1"
    assert _added_billing_records(mock_db) == [record]
    mock_db.session.commit.assert_called_once()


@patch("services.user_billing_service.db")
def test_admin_topup_rejects_tenant_the_account_does_not_belong_to(mock_db):
    with patch.object(UserBillingService, "_has_tenant_membership", return_value=False):
        with pytest.raises(ValueError, match="not a member"):
            UserBillingService.admin_topup(
                account_id="member-1",
                tenant_id="tenant-other",
                amount=Decimal(30),
            )

    mock_db.session.add.assert_not_called()
    mock_db.session.commit.assert_not_called()
