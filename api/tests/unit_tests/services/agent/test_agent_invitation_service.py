"""Unit tests for AgentInvitationService.

Code-generation and binding logic. The service is fully mock-driven
(see conftest.py for the rationale).
"""
from unittest.mock import MagicMock, patch

import pytest


@patch("services.agent.agent_invitation_service.db")
def test_generate_invitation_code_returns_unique_string_per_call(mock_db, agent_id):
    """Two consecutive calls return different codes; an anchor row is added each time."""
    from services.agent.agent_invitation_service import AgentInvitationService

    fake_agent = MagicMock(id=agent_id, account_id="acct-1")
    # First scalar() in the loop returns the agent; subsequent scalar()s
    # check for code collision (always None — no collision).
    mock_db.session.scalar.side_effect = [fake_agent, None, fake_agent, None]

    code1 = AgentInvitationService.generate_invitation_code(agent_id)
    code2 = AgentInvitationService.generate_invitation_code(agent_id)

    assert code1 != code2
    assert len(code1) >= 8
    # Each call adds one anchor row
    assert mock_db.session.add.call_count == 2


@patch("services.agent.agent_invitation_service.db")
def test_generate_invitation_code_rejects_unknown_agent(mock_db, agent_id):
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import AgentNotFoundError

    mock_db.session.scalar.return_value = None  # agent lookup fails

    with pytest.raises(AgentNotFoundError):
        AgentInvitationService.generate_invitation_code(agent_id)


@patch("services.agent.agent_invitation_service.db")
def test_bind_inserts_used_row_for_active_agent(
    mock_db, agent_id, invitee_account_id,
):
    """Happy bind: anchor lookup → agent active → no existing binding → INSERT."""
    from services.agent.agent_invitation_service import AgentInvitationService
    from models.agent import AgentStatus

    fake_anchor = MagicMock(agent_id=agent_id)
    fake_agent = MagicMock(
        id=agent_id, account_id="agent-acct", status=AgentStatus.ACTIVE.value,
    )
    # scalar() calls in order:
    #   1. anchor lookup
    #   2. agent lookup
    #   3. existing binding lookup (None — invitee not bound yet)
    mock_db.session.scalar.side_effect = [fake_anchor, fake_agent, None]

    result = AgentInvitationService.bind(
        invite_code="VALID_CODE", invitee_account_id=invitee_account_id,
    )

    assert result is fake_agent
    mock_db.session.add.assert_called_once()
    binding = mock_db.session.add.call_args[0][0]
    assert binding.invite_code == "VALID_CODE"
    assert binding.invitee_account_id == invitee_account_id
    assert binding.agent_id == agent_id
    assert binding.status == "used"


@patch("services.agent.agent_invitation_service.db")
def test_bind_rejects_empty_code(mock_db, invitee_account_id):
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import InvalidAgentInvitationCodeError

    with pytest.raises(InvalidAgentInvitationCodeError):
        AgentInvitationService.bind(invite_code="", invitee_account_id=invitee_account_id)
    with pytest.raises(InvalidAgentInvitationCodeError):
        AgentInvitationService.bind(invite_code="   ", invitee_account_id=invitee_account_id)


@patch("services.agent.agent_invitation_service.db")
def test_bind_rejects_unknown_code(mock_db, invitee_account_id):
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import InvalidAgentInvitationCodeError

    mock_db.session.scalar.return_value = None  # anchor not found

    with pytest.raises(InvalidAgentInvitationCodeError):
        AgentInvitationService.bind(invite_code="GHOST", invitee_account_id=invitee_account_id)


@patch("services.agent.agent_invitation_service.db")
def test_bind_rejects_suspended_agent(mock_db, agent_id, invitee_account_id):
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import AgentSuspendedError
    from models.agent import AgentStatus

    fake_anchor = MagicMock(agent_id=agent_id)
    suspended_agent = MagicMock(
        id=agent_id, account_id="x", status=AgentStatus.SUSPENDED.value,
    )
    mock_db.session.scalar.side_effect = [fake_anchor, suspended_agent]

    with pytest.raises(AgentSuspendedError):
        AgentInvitationService.bind(invite_code="C", invitee_account_id=invitee_account_id)


@patch("services.agent.agent_invitation_service.db")
def test_bind_rejects_self_invite(mock_db, agent_id, invitee_account_id):
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import SelfBindError
    from models.agent import AgentStatus

    fake_anchor = MagicMock(agent_id=agent_id)
    fake_agent = MagicMock(
        id=agent_id,
        account_id=invitee_account_id,  # SAME — self-invite
        status=AgentStatus.ACTIVE.value,
    )
    mock_db.session.scalar.side_effect = [fake_anchor, fake_agent]

    with pytest.raises(SelfBindError):
        AgentInvitationService.bind(invite_code="C", invitee_account_id=invitee_account_id)


@patch("services.agent.agent_invitation_service.db")
def test_bind_rejects_already_bound_invitee(mock_db, agent_id, invitee_account_id):
    from services.agent.agent_invitation_service import AgentInvitationService
    from services.errors.agent import AlreadyBoundError
    from models.agent import AgentStatus

    fake_anchor = MagicMock(agent_id=agent_id)
    fake_agent = MagicMock(
        id=agent_id, account_id="agent-acct", status=AgentStatus.ACTIVE.value,
    )
    existing_binding = MagicMock(agent_id="some-other-agent")
    mock_db.session.scalar.side_effect = [fake_anchor, fake_agent, existing_binding]

    with pytest.raises(AlreadyBoundError):
        AgentInvitationService.bind(invite_code="C", invitee_account_id=invitee_account_id)
