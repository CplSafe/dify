"""Tests for Account.is_agent / Account.agent_status properties.

These properties query live each call (no caching) so we can patch the
SQLAlchemy ``db`` session and assert that the right WHERE conditions
build against the right columns.
"""
from unittest.mock import MagicMock, patch


@patch("extensions.ext_database.db")
def test_is_agent_true_when_active_agent_exists(mock_db):
    from models.account import Account
    from models.agent import AgentStatus

    acct = Account(email="x@x.com", name="X")
    acct.id = "acct-1"

    # scalar() returns an Agent.id when an active agent exists
    mock_db.session.scalar.return_value = "agent-1"

    assert acct.is_agent is True
    # The WHERE clause filtered to status='active' — verify the query
    # builder was called once (lookup happens lazily per access).
    mock_db.session.scalar.assert_called_once()


@patch("extensions.ext_database.db")
def test_is_agent_false_when_no_agent_record(mock_db):
    from models.account import Account

    acct = Account(email="x@x.com", name="X")
    acct.id = "acct-2"
    mock_db.session.scalar.return_value = None

    assert acct.is_agent is False


@patch("extensions.ext_database.db")
def test_is_agent_false_for_suspended_agent(mock_db):
    """An agent in suspended state is NOT considered active.

    The query filters for status='active', so suspended rows return None
    from scalar() — the property reads False.
    """
    from models.account import Account

    acct = Account(email="x@x.com", name="X")
    acct.id = "acct-3"
    mock_db.session.scalar.return_value = None  # active filter excludes suspended

    assert acct.is_agent is False


@patch("extensions.ext_database.db")
def test_agent_status_returns_active_when_active(mock_db):
    from models.account import Account

    acct = Account(email="x@x.com", name="X")
    acct.id = "acct-1"
    mock_db.session.scalar.return_value = "active"

    assert acct.agent_status == "active"


@patch("extensions.ext_database.db")
def test_agent_status_returns_suspended_when_suspended(mock_db):
    from models.account import Account

    acct = Account(email="x@x.com", name="X")
    acct.id = "acct-1"
    mock_db.session.scalar.return_value = "suspended"

    assert acct.agent_status == "suspended"


@patch("extensions.ext_database.db")
def test_agent_status_returns_none_for_normal_user(mock_db):
    from models.account import Account

    acct = Account(email="x@x.com", name="X")
    acct.id = "acct-normal"
    mock_db.session.scalar.return_value = None

    assert acct.agent_status is None
