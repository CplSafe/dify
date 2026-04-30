"""Verify @agent_required:
- raises Forbidden when user has no Agent record
- raises Forbidden when agent is suspended
- passes through when agent is active and stashes agent on flask.g
"""
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import Forbidden


def _make_view():
    from controllers.console.wraps import agent_required

    @agent_required
    def view():
        return "OK"

    return view


def test_agent_required_blocks_non_agent():
    view = _make_view()
    fake_user = MagicMock(id="acct-no-agent")
    with patch("flask_login.utils._get_user", return_value=fake_user):
        with patch("controllers.console.wraps._lookup_agent", return_value=None):
            with pytest.raises(Forbidden):
                view()


def test_agent_required_blocks_suspended_agent():
    from models.agent import AgentStatus

    view = _make_view()
    suspended = MagicMock(status=AgentStatus.SUSPENDED.value)
    fake_user = MagicMock(id="acct-suspended")
    with patch("flask_login.utils._get_user", return_value=fake_user):
        with patch("controllers.console.wraps._lookup_agent", return_value=suspended):
            with pytest.raises(Forbidden):
                view()


def test_agent_required_allows_active_agent_and_stashes_on_g():
    from flask import Flask

    from models.agent import AgentStatus

    app = Flask(__name__)
    view = _make_view()
    active = MagicMock(status=AgentStatus.ACTIVE.value, id="agent-1")
    fake_user = MagicMock(id="acct-active")

    with app.test_request_context():
        from flask import g

        with patch("flask_login.utils._get_user", return_value=fake_user):
            with patch("controllers.console.wraps._lookup_agent", return_value=active):
                assert view() == "OK"
                assert g.current_agent is active
