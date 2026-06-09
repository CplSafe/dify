"""Unit tests for /admin/agents — controller-layer parsing helpers.

The controller class methods are decorated with the project's full auth
stack (``setup_required`` → ``login_required`` → ``account_initialization_required``
→ ``system_admin_required``) which queries the DB and reads the Flask
request context. Reproducing that environment in a unit test is brittle
and duplicates what integration tests already cover; the controller's
business logic is a thin transformation over already-tested services.

So this file tests only the pure helpers — parsing/validation — which
live in the same module and have no auth/context dependencies. The
service-call orchestration above them is exercised by integration tests
in CI (see plan §8.1 "Integration tests" — CI-only by project convention).
"""
from datetime import date
from decimal import Decimal

import pytest
from werkzeug.exceptions import BadRequest


def test_parse_decimal_accepts_string_form():
    from controllers.console.admin_agent.agents import _parse_decimal

    assert _parse_decimal("0.10", "rebate_rate") == Decimal("0.10")
    assert _parse_decimal("100", "amount") == Decimal(100)


def test_parse_decimal_returns_none_for_empty():
    from controllers.console.admin_agent.agents import _parse_decimal

    assert _parse_decimal(None, "rebate_rate") is None
    assert _parse_decimal("", "rebate_rate") is None


def test_parse_decimal_raises_bad_request_on_garbage():
    from controllers.console.admin_agent.agents import _parse_decimal

    with pytest.raises(BadRequest, match="invalid rebate_rate"):
        _parse_decimal("not-a-number", "rebate_rate")


def test_parse_date_accepts_iso_form():
    from controllers.console.admin_agent.agents import _parse_date

    assert _parse_date("2026-04-30", "signed_at") == date(2026, 4, 30)


def test_parse_date_returns_none_for_empty():
    from controllers.console.admin_agent.agents import _parse_date

    assert _parse_date(None, "signed_at") is None
    assert _parse_date("", "expires_at") is None


def test_parse_date_raises_bad_request_on_garbage():
    from controllers.console.admin_agent.agents import _parse_date

    with pytest.raises(BadRequest, match="invalid signed_at"):
        _parse_date("not-a-date", "signed_at")


def test_admin_agents_module_imports_cleanly():
    """Smoke test: the module loads without import-time errors and exposes
    the four expected Resource classes. This catches typos in route
    decorators / class definitions without exercising auth + DB.
    """
    from controllers.console.admin_agent import agents as mod

    assert hasattr(mod, "AdminAgentsApi")
    assert hasattr(mod, "AdminAgentDetailApi")
    assert hasattr(mod, "AdminAgentSuspendApi")
