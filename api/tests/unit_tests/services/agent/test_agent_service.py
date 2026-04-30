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
