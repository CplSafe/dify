"""Owner-only guard coverage for invitation and rebate endpoints.

Business rule: only workspace owners can

- issue / list / revoke registration invitation codes, and
- see rebate records & summary (rebates pay into the owner's workspace
  wallet — a member has no rebate account).

The ``@tenant_owner_required`` decorator's own role-check logic is covered
exhaustively by ``test_tenant_owner_required.py``. Here we lock in that
it's actually wired onto each protected view by exercising the behavior
end-to-end: a non-owner hitting any of these handlers must raise 403.

The full wrap chain applied by each view is (outer→inner):
    @setup_required
    @login_required
    @account_initialization_required
    @tenant_owner_required   ← the guard we care about
    def handler(self): ...

We peel the three outer decorators so the test doesn't depend on
setup/login DB state, but still calls the real ``tenant_owner_required``
wrapper — so if someone removes ``@tenant_owner_required`` the test
fails because the handler itself runs and the role check is gone.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import Forbidden

from controllers.console.creator import invitation as invitation_module
from controllers.console.creator import rebate as rebate_module
from models import Account
from models.account import TenantAccountRole


def _peel_outer_decorators(view, levels: int = 3):
    """Drop ``levels`` layers from the decorator chain.

    The three outer decorators (setup/login/account-init) are peeled so
    we land on the layer installed by ``@tenant_owner_required``.
    """
    current = view
    for _ in range(levels):
        current = current.__wrapped__
    return current


def _fake_account(role: TenantAccountRole | None) -> Account:
    account = MagicMock(spec=Account)
    account.current_role = role
    account.id = "u-1"
    return account


def _patched_current_user(account):
    mock = MagicMock()
    mock._get_current_object.return_value = account
    return patch("libs.login.current_user", new=mock)


NON_OWNER_ROLES = [
    TenantAccountRole.ADMIN,
    TenantAccountRole.EDITOR,
    TenantAccountRole.NORMAL,
    TenantAccountRole.DATASET_OPERATOR,
]


VIEWS_UNDER_GUARD = [
    ("invitation.list.get", invitation_module.InvitationListApi, "get"),
    ("invitation.list.post", invitation_module.InvitationListApi, "post"),
    ("invitation.item.delete", invitation_module.InvitationItemApi, "delete"),
    ("rebate.records.get", rebate_module.RebateRecordListApi, "get"),
    ("rebate.summary.get", rebate_module.RebateSummaryApi, "get"),
]


@pytest.mark.parametrize(("label", "cls", "method"), VIEWS_UNDER_GUARD)
@pytest.mark.parametrize("role", NON_OWNER_ROLES)
def test_non_owner_is_forbidden(label, cls, method, role):
    """Every owner-gated view must 403 for non-owners (incl. admins/editors)."""
    guarded = _peel_outer_decorators(getattr(cls, method))
    account = _fake_account(role)
    extra_args: tuple = ("inv-1",) if method == "delete" else ()
    with _patched_current_user(account):
        with pytest.raises(Forbidden):
            guarded(cls(), *extra_args)


@pytest.mark.parametrize(("label", "cls", "method"), VIEWS_UNDER_GUARD)
def test_missing_role_is_forbidden(label, cls, method):
    """Accounts with ``current_role == None`` must also be rejected.

    Covers the edge where a user has been removed from the tenant but
    still holds a valid session.
    """
    guarded = _peel_outer_decorators(getattr(cls, method))
    account = _fake_account(None)
    extra_args: tuple = ("inv-1",) if method == "delete" else ()
    with _patched_current_user(account):
        with pytest.raises(Forbidden):
            guarded(cls(), *extra_args)
