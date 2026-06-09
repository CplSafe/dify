"""Smoke tests for /agent/* console endpoints (parsers + module imports).

Auth + service orchestration is covered by integration tests; here we
test the pure parsing helpers and confirm each module loads cleanly.
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from werkzeug.exceptions import BadRequest


def test_dashboard_module_imports_cleanly():
    from controllers.console.agent_console import dashboard as mod

    assert hasattr(mod, "AgentDashboardApi")


def test_dashboard_stringify_decimals_helper():
    from controllers.console.agent_console.dashboard import _stringify_decimals

    out = _stringify_decimals({"withdrawable": Decimal("100.5"), "name": "x"})
    assert out["withdrawable"] == "100.5"
    assert out["name"] == "x"


def test_invitees_module_imports_cleanly():
    from controllers.console.agent_console import invitees as mod

    assert hasattr(mod, "AgentInviteesApi")


def test_invitations_module_imports_cleanly():
    from controllers.console.agent_console import invitations as mod

    assert hasattr(mod, "AgentInvitationsApi")


def test_withdrawals_module_imports_cleanly():
    from controllers.console.agent_console import withdrawals as mod

    assert hasattr(mod, "AgentWithdrawalsApi")


def test_parse_amount_accepts_decimal_string():
    from controllers.console.agent_console.withdrawals import _parse_amount

    assert _parse_amount("200.50") == Decimal("200.50")
    assert _parse_amount(100) == Decimal(100)


def test_parse_amount_rejects_missing():
    from controllers.console.agent_console.withdrawals import _parse_amount

    with pytest.raises(BadRequest, match="amount is required"):
        _parse_amount(None)
    with pytest.raises(BadRequest, match="amount is required"):
        _parse_amount("")


def test_parse_amount_rejects_garbage():
    from controllers.console.agent_console.withdrawals import _parse_amount

    with pytest.raises(BadRequest, match="invalid amount"):
        _parse_amount("not-a-number")


def test_withdrawal_serialize_uses_string_for_decimal():
    from controllers.console.agent_console.withdrawals import _serialize

    fake = MagicMock(
        id="req-1", amount=Decimal("200.50"),
        payout_method="alipay",
        payout_payload={"account": "x", "name": "y"},
        status="pending", review_note=None,
        created_at=datetime(2026, 4, 30, 10, 0, 0), reviewed_at=None,
    )
    out = _serialize(fake)
    assert out["amount"] == "200.50"
    assert out["status"] == "pending"
    assert out["created_at"] == "2026-04-30T10:00:00"
