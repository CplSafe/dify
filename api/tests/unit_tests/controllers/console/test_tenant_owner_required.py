"""Unit tests for the ``tenant_owner_required`` decorator.

Topup, allocation and other funds-movement endpoints must be gated on the
workspace OWNER role alone. Admin and editor roles are explicitly *not*
sufficient — this test suite locks that contract in.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import Forbidden

from controllers.console.wraps import tenant_owner_required
from models import Account
from models.account import TenantAccountRole


def _fake_account(role: TenantAccountRole | None) -> Account:
    """Return a MagicMock that passes isinstance(Account) checks."""
    account = MagicMock(spec=Account)
    account.current_role = role
    return account


@tenant_owner_required
def _protected_view() -> str:
    return "ok"


def _patched_current_user(account):
    """Patch ``libs.login.current_user`` with a MagicMock (not AsyncMock).

    Using ``new_callable=MagicMock`` is essential: the default auto-spec
    sees ``current_user`` as a proxy and synthesises an AsyncMock, which
    makes ``_get_current_object()`` return a coroutine instead of our
    account object.
    """
    mock = MagicMock()
    mock._get_current_object.return_value = account
    return patch("libs.login.current_user", new=mock)


class TestTenantOwnerRequired:
    def test_allows_owner(self):
        account = _fake_account(TenantAccountRole.OWNER)
        with _patched_current_user(account):
            assert _protected_view() == "ok"

    @pytest.mark.parametrize(
        "role",
        [
            TenantAccountRole.ADMIN,
            TenantAccountRole.EDITOR,
            TenantAccountRole.NORMAL,
            TenantAccountRole.DATASET_OPERATOR,
        ],
    )
    def test_rejects_non_owner_roles(self, role: TenantAccountRole):
        account = _fake_account(role)
        with _patched_current_user(account):
            with pytest.raises(Forbidden):
                _protected_view()

    def test_rejects_non_account_users(self):
        """End users and other non-Account principals must be rejected."""
        not_an_account = MagicMock()  # no spec → fails isinstance(Account)
        with _patched_current_user(not_an_account):
            with pytest.raises(Forbidden):
                _protected_view()

    def test_rejects_account_with_no_role(self):
        account = _fake_account(None)
        with _patched_current_user(account):
            with pytest.raises(Forbidden):
                _protected_view()
