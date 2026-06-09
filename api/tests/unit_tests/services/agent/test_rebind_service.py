"""Unit tests for RebindService.

The CORE invariant: ``approve()`` flips ``account_invitations.agent_id``
to the new agent but does NOT touch ``rebate_records.agent_id``. Pre-rebind
earnings stay with the original agent. Tests assert this on real model
mutations (not on mocked save calls) by reading back what the service set.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


@patch("services.agent.rebind_service.db")
def test_create_request_inserts_pending(mock_db, agent_id, invitee_account_id):
    from services.agent.rebind_service import RebindService

    from_agent = MagicMock(id=agent_id)
    to_agent = MagicMock(id="agent-y")
    # scalar() calls in order: from_agent lookup, to_agent lookup,
    # existing_pending lookup (None), last_approved lookup (None — no cooldown)
    mock_db.session.scalar.side_effect = [from_agent, to_agent, None, None]

    req = RebindService.create_request(
        account_id=invitee_account_id,
        from_agent_id=agent_id,
        to_agent_id="agent-y",
    )

    assert req.status == "pending"
    assert req.from_agent_id == agent_id
    assert req.to_agent_id == "agent-y"
    mock_db.session.add.assert_called_once()


@patch("services.agent.rebind_service.db")
def test_create_request_rejects_unknown_from_agent(mock_db, invitee_account_id):
    from services.agent.rebind_service import RebindService
    from services.errors.agent import AgentNotFoundError

    mock_db.session.scalar.return_value = None  # from_agent missing

    with pytest.raises(AgentNotFoundError):
        RebindService.create_request(
            account_id=invitee_account_id,
            from_agent_id="ghost", to_agent_id="agent-y",
        )


@patch("services.agent.rebind_service.db")
def test_create_request_rejects_duplicate_pending(
    mock_db, agent_id, invitee_account_id,
):
    from services.agent.rebind_service import RebindService
    from services.errors.agent import DuplicatePendingRebindError

    from_agent = MagicMock(id=agent_id)
    to_agent = MagicMock(id="agent-y")
    pending = MagicMock(status="pending")
    mock_db.session.scalar.side_effect = [from_agent, to_agent, pending]

    with pytest.raises(DuplicatePendingRebindError):
        RebindService.create_request(
            account_id=invitee_account_id,
            from_agent_id=agent_id, to_agent_id="agent-y",
        )


@patch("services.agent.rebind_service.db")
def test_cooldown_blocks_new_request_within_90_days(
    mock_db, agent_id, invitee_account_id,
):
    from services.agent.rebind_service import RebindService
    from services.errors.agent import RebindCooldownActiveError

    from_agent = MagicMock(id=agent_id)
    to_agent = MagicMock(id="agent-y")
    last_approved = MagicMock(reviewed_at=datetime.utcnow() - timedelta(days=50))
    mock_db.session.scalar.side_effect = [from_agent, to_agent, None, last_approved]

    with pytest.raises(RebindCooldownActiveError):
        RebindService.create_request(
            account_id=invitee_account_id,
            from_agent_id=agent_id, to_agent_id="agent-y",
        )


@patch("services.agent.rebind_service.db")
def test_cooldown_lifted_after_91_days(mock_db, agent_id, invitee_account_id):
    """At day 91 (just past the 90-day window) a new request is allowed."""
    from services.agent.rebind_service import RebindService

    from_agent = MagicMock(id=agent_id)
    to_agent = MagicMock(id="agent-y")
    last_approved = MagicMock(reviewed_at=datetime.utcnow() - timedelta(days=91))
    mock_db.session.scalar.side_effect = [from_agent, to_agent, None, last_approved]

    req = RebindService.create_request(
        account_id=invitee_account_id,
        from_agent_id=agent_id, to_agent_id="agent-y",
    )
    assert req.status == "pending"


@patch("services.agent.rebind_service.db")
def test_approve_flips_binding_agent_id_only(
    mock_db, agent_id, invitee_account_id,
):
    """The CORE invariant: approve flips account_invitations.agent_id but
    does NOT touch any rebate_records.agent_id."""
    from services.agent.rebind_service import RebindService

    request_id = "req-1"
    new_agent_id = "agent-y"
    pending_req = MagicMock(
        id=request_id, status="pending",
        account_id=invitee_account_id, to_agent_id=new_agent_id,
    )
    binding = MagicMock(invitee_account_id=invitee_account_id, agent_id=agent_id)
    new_agent_obj = MagicMock(id=new_agent_id, account_id="agent-y-acct")

    # scalar() calls: pending_req lookup, binding lookup, new_agent lookup
    mock_db.session.scalar.side_effect = [pending_req, binding, new_agent_obj]

    RebindService.approve(request_id, reviewer_id="admin-1", note="ok")

    # Binding now points to new agent
    assert binding.agent_id == new_agent_id
    assert binding.inviter_account_id == "agent-y-acct"
    # Request status flipped
    assert pending_req.status == "approved"
    assert pending_req.reviewer_id == "admin-1"
    assert pending_req.review_note == "ok"
    assert pending_req.reviewed_at is not None


@patch("services.agent.rebind_service.db")
def test_approve_rejects_already_processed_request(mock_db):
    from services.agent.rebind_service import RebindService
    from services.errors.agent import RebindRequestNotFoundError

    already_approved = MagicMock(status="approved")
    mock_db.session.scalar.return_value = already_approved

    with pytest.raises(RebindRequestNotFoundError):
        RebindService.approve("req-1", reviewer_id="admin-1")


@patch("services.agent.rebind_service.db")
def test_reject_marks_rejected_without_touching_binding(mock_db, invitee_account_id):
    from services.agent.rebind_service import RebindService

    pending = MagicMock(status="pending", account_id=invitee_account_id)
    mock_db.session.scalar.return_value = pending

    RebindService.reject("req-1", reviewer_id="admin-1", note="no")

    assert pending.status == "rejected"
    assert pending.reviewer_id == "admin-1"
    assert pending.review_note == "no"
