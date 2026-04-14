"""Unit tests for the workspace wallet read endpoint.

These exercise the controller's serialisation contract — that the
response bundles both tenant-level and user-level balances, and that
balances are exposed as strings (never floats) so callers never round
fractional cents.
"""

from __future__ import annotations

import builtins
import importlib
import sys
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from flask.views import MethodView

# ``controllers.console.workspace.load_balancing_config`` relies on MethodView
# being a builtin — mirror that shim here so collection order doesn't matter.
if not hasattr(builtins, "MethodView"):
    builtins.MethodView = MethodView  # type: ignore[attr-defined]


@pytest.fixture
def topup_module(monkeypatch: pytest.MonkeyPatch):
    """Reload the topup controller with auth decorators no-oped.

    Without this, invoking the Resource method triggers ``setup_required``
    which tries to hit the real DB in a unit-test context.
    """
    from controllers.console import console_ns, wraps
    from libs import login

    def _noop(func):
        return func

    monkeypatch.setattr(login, "login_required", _noop)
    monkeypatch.setattr(wraps, "setup_required", _noop)
    monkeypatch.setattr(wraps, "account_initialization_required", _noop)

    def _noop_route(*args, **kwargs):
        def _decorator(cls):
            return cls

        return _decorator

    monkeypatch.setattr(console_ns, "route", _noop_route)

    module_name = "controllers.console.workspace.topup"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _fake_tenant_balance() -> MagicMock:
    balance = MagicMock()
    balance.tenant_id = "tenant-1"
    balance.balance = Decimal("123.45")
    balance.locked = Decimal("10.00")
    balance.total_topup = Decimal("200.00")
    balance.total = Decimal("133.45")
    balance.currency = "CNY"
    balance.updated_at = datetime(2026, 4, 14, 12, 0, 0)
    return balance


def _fake_user_balance() -> MagicMock:
    balance = MagicMock()
    balance.account_id = "acct-1"
    balance.balance = Decimal("8.00")
    balance.currency = "CNY"
    balance.is_sufficient.return_value = True
    balance.updated_at = datetime(2026, 4, 14, 12, 0, 1)
    return balance


class TestWorkspaceWalletApi:
    def test_bundles_tenant_and_user_balances(self, topup_module, monkeypatch):
        account = MagicMock()
        account.id = "acct-1"
        monkeypatch.setattr(
            topup_module, "current_account_with_tenant", lambda: (account, "tenant-1")
        )

        tenant_balance = _fake_tenant_balance()
        user_balance = _fake_user_balance()
        monkeypatch.setattr(
            topup_module.TenantBalanceService,
            "get_or_create",
            classmethod(lambda cls, tenant_id: tenant_balance),
        )
        monkeypatch.setattr(
            topup_module.UserBillingService,
            "get_or_create_balance",
            classmethod(lambda cls, account_id: user_balance),
        )

        body, status = topup_module.WorkspaceWalletApi().get()

        assert status == 200
        assert body["tenant"] == {
            "tenant_id": "tenant-1",
            "balance": "123.45",
            "locked": "10.00",
            "total_topup": "200.00",
            "total": "133.45",
            "currency": "CNY",
            "updated_at": "2026-04-14T12:00:00",
        }
        assert body["user"] == {
            "account_id": "acct-1",
            "balance": "8.00",
            "currency": "CNY",
            "is_sufficient": True,
            "updated_at": "2026-04-14T12:00:01",
        }

    def test_amounts_serialised_as_strings_not_floats(self, topup_module, monkeypatch):
        """Regression guard: JSON float round-tripping loses fractional cents."""
        account = MagicMock()
        account.id = "acct-1"
        monkeypatch.setattr(
            topup_module, "current_account_with_tenant", lambda: (account, "tenant-1")
        )
        monkeypatch.setattr(
            topup_module.TenantBalanceService,
            "get_or_create",
            classmethod(lambda cls, tenant_id: _fake_tenant_balance()),
        )
        monkeypatch.setattr(
            topup_module.UserBillingService,
            "get_or_create_balance",
            classmethod(lambda cls, account_id: _fake_user_balance()),
        )

        body, _ = topup_module.WorkspaceWalletApi().get()

        for key in ("balance", "locked", "total_topup", "total"):
            assert isinstance(body["tenant"][key], str)
        assert isinstance(body["user"]["balance"], str)
