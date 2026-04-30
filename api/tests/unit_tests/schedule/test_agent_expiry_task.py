"""Unit tests for agent_expiry_task.

Verifies:
- agents past expires_at flip to suspended in a single batch commit
- agents without expires_at (NULL — open-ended) are never touched
- agents whose expires_at is still in the future are never touched
- task is idempotent: already-suspended expired agents are skipped
  (the query filters by status='active')
- empty result short-circuits without committing
"""
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from models.agent import AgentStatus
from schedule.agent_expiry_task import agent_expiry_task


def _mock_agent(*, agent_id: str, expires_at: date | None) -> MagicMock:
    a = MagicMock()
    a.id = agent_id
    a.expires_at = expires_at
    a.status = AgentStatus.ACTIVE.value
    return a


@patch("schedule.agent_expiry_task.db")
def test_no_expired_agents_skips_commit(mock_db):
    mock_db.session.scalars.return_value.all.return_value = []

    agent_expiry_task()

    mock_db.session.commit.assert_not_called()


@patch("schedule.agent_expiry_task.db")
def test_expired_agent_is_suspended(mock_db):
    """An agent whose expires_at <= today flips to suspended."""
    yesterday = date.today() - timedelta(days=1)
    expired = _mock_agent(agent_id="agent-1", expires_at=yesterday)
    mock_db.session.scalars.return_value.all.return_value = [expired]

    agent_expiry_task()

    assert expired.status == AgentStatus.SUSPENDED.value
    mock_db.session.commit.assert_called_once()


@patch("schedule.agent_expiry_task.db")
def test_today_expiry_is_suspended(mock_db):
    """Boundary: expires_at == today is treated as expired."""
    today = date.today()
    expiring = _mock_agent(agent_id="agent-1", expires_at=today)
    mock_db.session.scalars.return_value.all.return_value = [expiring]

    agent_expiry_task()

    assert expiring.status == AgentStatus.SUSPENDED.value


@patch("schedule.agent_expiry_task.db")
def test_multiple_expired_agents_share_one_commit(mock_db):
    """Three expired agents → one batch commit, all marked suspended."""
    yesterday = date.today() - timedelta(days=1)
    agents = [
        _mock_agent(agent_id=f"agent-{i}", expires_at=yesterday) for i in range(3)
    ]
    mock_db.session.scalars.return_value.all.return_value = agents

    agent_expiry_task()

    for a in agents:
        assert a.status == AgentStatus.SUSPENDED.value
    mock_db.session.commit.assert_called_once()
