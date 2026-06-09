"""Smoke tests for /admin/withdrawals endpoints."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock


def test_withdrawal_review_module_imports_cleanly():
    from controllers.console.admin_agent import withdrawal_review as mod

    assert hasattr(mod, "AdminWithdrawalsApi")
    assert hasattr(mod, "AdminWithdrawalPayApi")
    assert hasattr(mod, "AdminWithdrawalRejectApi")


def test_serialize_emits_expected_keys_with_decimal_as_string():
    from controllers.console.admin_agent.withdrawal_review import _serialize

    fake = MagicMock(
        id="req-1", agent_id="agent-1", amount=Decimal("200.50"),
        payout_method="alipay",
        payout_payload={"account": "x@y.com", "name": "张三"},
        status="pending", reviewer_id=None, review_note=None,
        created_at=datetime(2026, 4, 30, 12, 0, 0), reviewed_at=None,
    )
    out = _serialize(fake)
    assert set(out.keys()) == {
        "id", "agent_id", "amount", "payout_method", "payout_payload",
        "status", "reviewer_id", "review_note", "created_at", "reviewed_at",
    }
    # Decimal serialised as string so JSON precision survives
    assert out["amount"] == "200.50"
    assert out["payout_payload"]["name"] == "张三"
