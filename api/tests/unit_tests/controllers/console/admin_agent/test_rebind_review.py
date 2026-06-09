"""Smoke tests for /admin/rebind-requests endpoints.

Per project convention (see ``test_admin.py``) controller-layer auth +
HTTP wrapping is exercised by integration tests; here we just confirm
the module imports and the serializer helper produces the right shape.
Service-level behaviour (cooldown, approve preserves rebate history,
etc.) is fully covered in ``test_rebind_service.py``.
"""
from datetime import datetime
from unittest.mock import MagicMock


def test_rebind_review_module_imports_cleanly():
    from controllers.console.admin_agent import rebind_review as mod

    assert hasattr(mod, "AdminRebindRequestsApi")
    assert hasattr(mod, "AdminRebindApproveApi")
    assert hasattr(mod, "AdminRebindRejectApi")


def test_serialize_emits_expected_keys():
    from controllers.console.admin_agent.rebind_review import _serialize

    fake = MagicMock(
        id="req-1", account_id="acct-1",
        from_agent_id="from", to_agent_id="to",
        status="pending", reviewer_id=None, review_note=None,
        created_at=datetime(2026, 4, 30, 12, 0, 0),
        reviewed_at=None,
    )
    out = _serialize(fake)
    assert set(out.keys()) == {
        "id", "account_id", "from_agent_id", "to_agent_id",
        "status", "reviewer_id", "review_note", "created_at", "reviewed_at",
    }
    assert out["created_at"] == "2026-04-30T12:00:00"
    assert out["reviewed_at"] is None


def test_serialize_handles_reviewed_request():
    from controllers.console.admin_agent.rebind_review import _serialize

    fake = MagicMock(
        id="req-1", account_id="acct-1",
        from_agent_id="from", to_agent_id="to",
        status="approved", reviewer_id="admin-1", review_note="ok",
        created_at=datetime(2026, 4, 30, 12, 0, 0),
        reviewed_at=datetime(2026, 4, 30, 13, 0, 0),
    )
    out = _serialize(fake)
    assert out["status"] == "approved"
    assert out["reviewer_id"] == "admin-1"
    assert out["reviewed_at"] == "2026-04-30T13:00:00"
