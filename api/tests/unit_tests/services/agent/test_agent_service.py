"""Unit tests for AgentService.

Tests follow the project's prevailing service-test pattern: ``db`` is
patched at the module level and assertions are made on session.add /
flush / commit calls + the objects passed to them. No real DB engine.
"""
from unittest.mock import MagicMock, patch

import pytest


@patch("services.agent.agent_service.db")
def test_create_agent_inserts_agent_and_wallet(mock_db, make_agent_kwargs):
    """Happy path: creating an agent must add Agent AND AgentWallet to
    the session in the same logical operation. Caller commits."""
    from services.agent.agent_service import AgentService

    # No existing agent for this account_id
    mock_db.session.scalar.return_value = None

    agent = AgentService.create_agent(**make_agent_kwargs)

    # Agent's defaults are populated
    assert agent.account_id == make_agent_kwargs["account_id"]
    assert agent.name == "Test Agent"
    assert agent.created_by == make_agent_kwargs["created_by"]

    # add called twice: once for Agent, once for AgentWallet.
    # flush called between to populate agent.id before wallet references it.
    assert mock_db.session.add.call_count == 2
    mock_db.session.flush.assert_called_once()
    # Service does NOT commit — caller owns the transaction
    mock_db.session.commit.assert_not_called()


@patch("services.agent.agent_service.db")
def test_create_agent_rejects_duplicate_account(mock_db, make_agent_kwargs):
    """If account_id already has an Agent row, raise instead of creating a 2nd."""
    from services.agent.agent_service import AgentService
    from services.errors.agent import AgentAccountAlreadyExistsError

    existing = MagicMock()  # any truthy value triggers the guard
    mock_db.session.scalar.return_value = existing

    with pytest.raises(AgentAccountAlreadyExistsError):
        AgentService.create_agent(**make_agent_kwargs)

    mock_db.session.add.assert_not_called()


@patch("services.agent.agent_service.db")
def test_suspend_agent_sets_status_to_suspended(mock_db, agent_id):
    from services.agent.agent_service import AgentService
    from models.agent import AgentStatus

    fake_agent = MagicMock(id=agent_id, status=AgentStatus.ACTIVE.value)
    mock_db.session.scalar.return_value = fake_agent

    result = AgentService.suspend_agent(agent_id)

    assert result.status == AgentStatus.SUSPENDED.value
    assert fake_agent.status == AgentStatus.SUSPENDED.value
    mock_db.session.commit.assert_not_called()


@patch("services.agent.agent_service.db")
def test_suspend_agent_raises_when_missing(mock_db, agent_id):
    from services.agent.agent_service import AgentService
    from services.errors.agent import AgentNotFoundError

    mock_db.session.scalar.return_value = None

    with pytest.raises(AgentNotFoundError):
        AgentService.suspend_agent(agent_id)


@patch("services.agent.agent_service.db")
def test_update_agent_allows_whitelisted_fields(mock_db, agent_id):
    from decimal import Decimal
    from services.agent.agent_service import AgentService

    fake_agent = MagicMock(id=agent_id)
    mock_db.session.scalar.return_value = fake_agent

    AgentService.update_agent(agent_id, rebate_rate=Decimal("0.15"), notes="bumped")

    assert fake_agent.rebate_rate == Decimal("0.15")
    assert fake_agent.notes == "bumped"


@patch("services.agent.agent_service.db")
def test_update_agent_rejects_non_whitelisted_field(mock_db, agent_id):
    """status is intentionally NOT updatable here — caller must use suspend_agent."""
    from services.agent.agent_service import AgentService

    fake_agent = MagicMock(id=agent_id)
    mock_db.session.scalar.return_value = fake_agent

    with pytest.raises(ValueError, match="not updatable"):
        AgentService.update_agent(agent_id, status="suspended")
