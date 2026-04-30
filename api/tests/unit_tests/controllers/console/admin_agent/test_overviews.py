"""Smoke tests for /admin/rebate-records and /admin/agent-consumption."""
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from werkzeug.exceptions import BadRequest


def test_overviews_module_imports_cleanly():
    from controllers.console.admin_agent import overviews as mod

    assert hasattr(mod, "AdminRebateRecordsApi")
    assert hasattr(mod, "AdminAgentConsumptionApi")


def test_parse_iso_date_returns_date_for_valid_input():
    from controllers.console.admin_agent.overviews import _parse_iso_date

    assert _parse_iso_date("2026-04-30", "from") == date(2026, 4, 30)


def test_parse_iso_date_returns_none_for_empty():
    from controllers.console.admin_agent.overviews import _parse_iso_date

    assert _parse_iso_date(None, "from") is None
    assert _parse_iso_date("", "to") is None


def test_parse_iso_date_raises_on_garbage():
    from controllers.console.admin_agent.overviews import _parse_iso_date

    with pytest.raises(BadRequest, match="invalid from"):
        _parse_iso_date("yesterday", "from")


def test_serialize_rebate_record_emits_decimals_as_strings():
    from controllers.console.admin_agent.overviews import _serialize_rebate_record

    fake = MagicMock(
        id="r-1", inviter_account_id="inv", agent_id="ag",
        invitee_account_id="ee", settlement_date="2026-04-30",
        consumption_amount=Decimal("100.5"), rebate_amount=Decimal("10.05"),
        status="settled",
        created_at=datetime(2026, 4, 30, 1, 0, 0),
    )
    out = _serialize_rebate_record(fake)
    assert out["consumption_amount"] == "100.5"
    assert out["rebate_amount"] == "10.05"
    assert out["created_at"] == "2026-04-30T01:00:00"
