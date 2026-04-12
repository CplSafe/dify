"""User balance and billing record endpoints."""

from decimal import Decimal, InvalidOperation

from flask import request
from flask_restx import Resource

from controllers.console import console_ns
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from services.user_billing_service import UserBillingService


def _require_system_admin(user):
    if not user.is_system_admin:
        from werkzeug.exceptions import Forbidden
        raise Forbidden("Only system administrators can access this endpoint")


@console_ns.route("/creator/balance")
class UserBalanceApi(Resource):
    """Get current user's balance."""

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        current_user, _ = current_account_with_tenant()
        balance = UserBillingService.get_or_create_balance(current_user.id)
        return {
            "account_id": balance.account_id,
            "balance": str(balance.balance),
            "currency": balance.currency,
            "is_sufficient": balance.is_sufficient(),
        }


@console_ns.route("/creator/admin/balances")
class AdminBalancesApi(Resource):
    """List all user balances (super admin only)."""

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))

        balances, total = UserBillingService.get_all_balances(limit=limit, offset=offset)

        # Enrich with account names
        from sqlalchemy import select

        from models.account import Account
        from models.engine import db

        result = []
        for b in balances:
            account = db.session.scalar(select(Account).where(Account.id == b.account_id))
            result.append({
                "account_id": b.account_id,
                "account_name": account.name if account else "",
                "account_email": account.email if account else "",
                "balance": str(b.balance),
                "currency": b.currency,
                "is_sufficient": b.is_sufficient(),
                "updated_at": b.updated_at.isoformat(),
            })

        return {"data": result, "total": total, "limit": limit, "offset": offset}


@console_ns.route("/creator/admin/topup")
class AdminTopupApi(Resource):
    """Top up a user's balance (super admin only)."""

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        payload = request.get_json() or {}
        account_id = payload.get("account_id")
        raw_amount = payload.get("amount")
        description = payload.get("description", "")

        if not account_id or raw_amount is None:
            from werkzeug.exceptions import BadRequest
            raise BadRequest("account_id and amount are required")

        try:
            amount = Decimal(str(raw_amount))
        except InvalidOperation:
            from werkzeug.exceptions import BadRequest
            raise BadRequest("Invalid amount")

        record = UserBillingService.topup(
            account_id=account_id,
            amount=amount,
            description=description,
        )
        return record.to_dict(), 201


@console_ns.route("/creator/billing/records")
class BillingRecordsApi(Resource):
    """List billing records for the current user."""

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        current_user, _ = current_account_with_tenant()
        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))

        records, total = UserBillingService.get_billing_records(
            current_user.id, limit=limit, offset=offset
        )
        return {
            "data": [r.to_dict() for r in records],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@console_ns.route("/creator/admin/billing/records")
class AdminBillingRecordsApi(Resource):
    """List all billing records (super admin only)."""

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        current_user, _ = current_account_with_tenant()
        _require_system_admin(current_user)

        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))
        tenant_id = request.args.get("tenant_id")
        account_id = request.args.get("account_id")

        records, total = UserBillingService.get_all_billing_records(
            tenant_id=tenant_id, account_id=account_id, limit=limit, offset=offset
        )
        return {
            "data": [r.to_dict() for r in records],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
