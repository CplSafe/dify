"""Smoke tests for /agent/bind/* endpoints + public-view whitelist."""
from unittest.mock import MagicMock


def test_bind_module_imports_cleanly():
    from controllers.console.agent_console import bind as mod

    assert hasattr(mod, "AgentBindPreviewApi")
    assert hasattr(mod, "AgentBindConfirmApi")
    assert hasattr(mod, "AgentRebindRequestApi")


def test_public_agent_view_strips_internal_fields():
    """preview endpoint must NOT leak rebate_rate / contact_phone / notes /
    expires_at / created_by / id / account_id — those are operator-internal.
    """
    from controllers.console.agent_console.bind import _public_agent_view

    fake = MagicMock()
    # Set sensitive fields that should NOT appear in output
    fake.id = "agent-1"
    fake.account_id = "acct-1"
    fake.contact_phone = "13800000000"
    fake.notes = "secret note"
    fake.rebate_rate = "0.10"
    fake.expires_at = "2027-04-30"
    fake.created_by = "admin-1"
    # Allowed fields
    fake.name = "Test Agent"
    fake.level = "province"
    fake.region_province = "广东"
    fake.region_city = None

    out = _public_agent_view(fake)

    assert set(out.keys()) == {"name", "level", "region_province", "region_city"}
    # Sensitive fields explicitly absent
    assert "id" not in out
    assert "account_id" not in out
    assert "contact_phone" not in out
    assert "notes" not in out
    assert "rebate_rate" not in out
    assert "expires_at" not in out
    assert "created_by" not in out
