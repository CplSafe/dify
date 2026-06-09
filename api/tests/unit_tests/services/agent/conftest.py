"""Shared fixtures for agent service tests.

We follow the project's prevailing pattern: services are tested by
patching ``db`` (and any peer services) at the module level. We do NOT
spin up a real engine here — a plan-doc fixture named ``app_with_db``
was contemplated but ``api/tests/unit_tests/conftest.py`` already
provides an autouse Flask app context backed by an in-memory SQLite
session, and SQLite cannot model the ``JSONB`` column or partial unique
indexes on the agent schema. Tests use mocks instead.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest


@pytest.fixture
def admin_account_id() -> str:
    return str(uuid4())


@pytest.fixture
def agent_account_id() -> str:
    return str(uuid4())


@pytest.fixture
def invitee_account_id() -> str:
    return str(uuid4())


@pytest.fixture
def agent_id() -> str:
    return str(uuid4())


@pytest.fixture
def make_agent_kwargs(agent_account_id: str, admin_account_id: str) -> dict:
    """Default kwargs for AgentService.create_agent."""
    return {
        "account_id": agent_account_id,
        "name": "Test Agent",
        "rebate_rate": Decimal("0.10"),
        "level": "province",
        "region_province": "广东",
        "region_city": None,
        "contact_phone": "13800000000",
        "notes": None,
        "signed_at": date(2026, 4, 30),
        "expires_at": date(2027, 4, 30),
        "created_by": admin_account_id,
    }
