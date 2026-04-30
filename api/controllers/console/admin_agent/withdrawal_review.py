"""Sysadmin endpoints for reviewing withdrawal requests.

Routes (under /console/api):

- GET   /admin/withdrawals                       list (paginated, status filter)
- POST  /admin/withdrawals/<request_id>/pay      mark as paid + decrement wallet
- POST  /admin/withdrawals/<request_id>/reject   mark as rejected (wallet untouched)
"""
from __future__ import annotations

from flask import request
from flask_login import current_user
from flask_restx import Resource
from sqlalchemy import select
from werkzeug.exceptions import BadRequest, NotFound

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
    system_admin_required,
)
from extensions.ext_database import db
from libs.login import login_required
from models.agent import WithdrawalRequest
from services.agent.withdrawal_service import WithdrawalService
from services.errors.agent import (
    InsufficientWithdrawableBalanceError,
    WithdrawalRequestNotFoundError,
)


def _serialize(req: WithdrawalRequest) -> dict:
    return {
        "id": req.id,
        "agent_id": req.agent_id,
        "amount": str(req.amount),
        "payout_method": req.payout_method,
        "payout_payload": req.payout_payload,
        "status": req.status,
        "reviewer_id": req.reviewer_id,
        "review_note": req.review_note,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
    }


@console_ns.route("/admin/withdrawals")
class AdminWithdrawalsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def get(self) -> dict:
        page = max(1, int(request.args.get("page", 1)))
        limit = min(100, max(1, int(request.args.get("limit", 20))))
        status = request.args.get("status")

        stmt = select(WithdrawalRequest).order_by(WithdrawalRequest.created_at.desc())
        if status:
            stmt = stmt.where(WithdrawalRequest.status == status)

        offset = (page - 1) * limit
        rows = db.session.scalars(stmt.offset(offset).limit(limit)).all()
        return {
            "data": [_serialize(r) for r in rows],
            "page": page,
            "limit": limit,
            "has_more": len(rows) == limit,
        }


@console_ns.route("/admin/withdrawals/<string:request_id>/pay")
class AdminWithdrawalPayApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def post(self, request_id: str) -> dict:
        body = request.get_json(silent=True) or {}
        transaction_id = body.get("transaction_id")
        if not transaction_id:
            raise BadRequest("transaction_id is required")
        try:
            req = WithdrawalService.mark_paid(
                request_id,
                reviewer_id=current_user.id,
                transaction_id=transaction_id,
            )
            db.session.commit()
        except WithdrawalRequestNotFoundError as exc:
            db.session.rollback()
            raise NotFound(str(exc)) from exc
        except InsufficientWithdrawableBalanceError as exc:
            db.session.rollback()
            raise BadRequest(str(exc)) from exc
        return _serialize(req)


@console_ns.route("/admin/withdrawals/<string:request_id>/reject")
class AdminWithdrawalRejectApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def post(self, request_id: str) -> dict:
        body = request.get_json(silent=True) or {}
        note = body.get("note")
        if not note:
            raise BadRequest("note is required for rejection")
        try:
            req = WithdrawalService.reject(
                request_id, reviewer_id=current_user.id, note=note,
            )
            db.session.commit()
        except WithdrawalRequestNotFoundError as exc:
            db.session.rollback()
            raise NotFound(str(exc)) from exc
        return _serialize(req)
