"""Workspace wallet and top-up endpoints.

Surfaces the workspace-level ``TenantBalance`` (balance / locked /
total_topup) together with the caller's own ``UserBalance`` so the
frontend wallet widget can render both in a single request.

Any member of the workspace may read their wallet; mutation endpoints
(topup creation, allocations) live below and are gated on the OWNER
role via ``@tenant_owner_required``.
"""

from __future__ import annotations

from flask_restx import Resource

from controllers.console import console_ns
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from services.user_billing_service import UserBillingService
from services.wallet.tenant_balance_service import TenantBalanceService


def _tenant_balance_payload(tenant_id: str) -> dict:
    balance = TenantBalanceService.get_or_create(tenant_id)
    return {
        "tenant_id": balance.tenant_id,
        "balance": str(balance.balance),
        "locked": str(balance.locked),
        "total_topup": str(balance.total_topup),
        "total": str(balance.total),
        "currency": balance.currency,
        "updated_at": balance.updated_at.isoformat(),
    }


def _user_balance_payload(account_id: str) -> dict:
    balance = UserBillingService.get_or_create_balance(account_id)
    return {
        "account_id": balance.account_id,
        "balance": str(balance.balance),
        "currency": balance.currency,
        "is_sufficient": balance.is_sufficient(),
        "updated_at": balance.updated_at.isoformat(),
    }


@console_ns.route("/workspaces/current/wallet")
class WorkspaceWalletApi(Resource):
    """Return the current workspace wallet plus the caller's member balance."""

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        current_user, current_tenant_id = current_account_with_tenant()
        return {
            "tenant": _tenant_balance_payload(current_tenant_id),
            "user": _user_balance_payload(current_user.id),
        }, 200
