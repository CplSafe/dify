"""Unit tests for payment-related models."""
from decimal import Decimal

from models.creator import (
    AllocationRecord,
    BillingRecord,
    BillingRecordType,
    PaymentOrder,
    PaymentProviderName,
    TenantBalance,
)


class TestPaymentProviderName:
    def test_alipay_qr_value(self):
        assert PaymentProviderName.ALIPAY_QR.value == "alipay_qr"

    def test_alipay_page_value(self):
        assert PaymentProviderName.ALIPAY_PAGE.value == "alipay_page"

    def test_wechat_value(self):
        assert PaymentProviderName.WECHAT.value == "wechat"


class TestTenantBalance:
    def test_default_values(self):
        b = TenantBalance(tenant_id="t1")
        assert b.balance == Decimal(0)
        assert b.locked == Decimal(0)
        assert b.total_topup == Decimal(0)
        assert b.currency == "CNY"

    def test_total_property(self):
        b = TenantBalance(tenant_id="t1")
        b.balance = Decimal(100)
        b.locked = Decimal(50)
        assert b.total == Decimal(150)


class TestPaymentOrder:
    def test_required_fields(self):
        o = PaymentOrder(
            provider="alipay_qr",
            out_trade_no="abc",
            tenant_id="t1",
            account_id="a1",
            amount=Decimal(10),
            amount_fen=1000,
            subject="test",
            status="pending",
            expires_at=None,  # set in real test below
        )
        assert o.provider == "alipay_qr"
        assert o.amount_fen == 1000


class TestAllocationRecord:
    def test_signed_amount(self):
        positive = AllocationRecord(
            tenant_id="t1",
            account_id="a1",
            operator_id="op1",
            amount=Decimal(50),
        )
        negative = AllocationRecord(
            tenant_id="t1",
            account_id="a1",
            operator_id="op1",
            amount=Decimal(-30),
        )
        assert positive.amount > 0
        assert negative.amount < 0


class TestBillingRecordType:
    def test_allocation_enum(self):
        assert BillingRecordType.ALLOCATION.value == "allocation"


class TestBillingRecordScope:
    def test_scope_defaults_to_user(self):
        r = BillingRecord(account_id="a1", amount=Decimal(1), record_type="topup")
        assert r.scope == "user"

    def test_scope_can_be_tenant(self):
        r = BillingRecord(
            account_id="a1", amount=Decimal(1), record_type="topup", scope="tenant"
        )
        assert r.scope == "tenant"

    def test_to_dict_includes_scope(self):
        r = BillingRecord(account_id="a1", amount=Decimal(1), record_type="topup")
        # created_at is server-assigned; to_dict needs a value to call isoformat()
        from datetime import datetime

        r.created_at = datetime(2026, 1, 1)
        assert r.to_dict()["scope"] == "user"
