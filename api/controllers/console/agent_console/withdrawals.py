"""Agent console — withdrawal requests.

Routes:

- POST /agent/withdrawals       create a payout request (drafts pending; sysadmin marks paid)
- GET  /agent/withdrawals       this agent's request history (paginated)
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import g, request
from flask_restx import Resource
from sqlalchemy import select
from werkzeug.exceptions import BadRequest

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    agent_required,
    setup_required,
)
from extensions.ext_database import db
from libs.login import login_required
from models.agent import WithdrawalRequest
from services.agent.withdrawal_service import WithdrawalService
from services.errors.agent import (
    DuplicatePendingWithdrawalError,
    InsufficientWithdrawableBalanceError,
    WithdrawalAmountTooSmallError,
)


def _parse_amount(raw: object) -> Decimal:
    if raw is None or raw == "":
        raise BadRequest("amount is required")
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError) as exc:
        raise BadRequest(f"invalid amount: {raw!r}") from exc


def _serialize(req: WithdrawalRequest) -> dict:
    return {
        "id": req.id,
        "amount": str(req.amount),
        "payout_method": req.payout_method,
        "payout_payload": req.payout_payload,
        "status": req.status,
        "review_note": req.review_note,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
    }


@console_ns.route("/agent/withdrawals")
class AgentWithdrawalsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @agent_required
    def post(self) -> tuple[dict, int]:
        agent = g.current_agent
        body = request.get_json(silent=True) or {}
        try:
            payout_method = body["payout_method"]
            payout_payload = body.get("payout_payload") or {}
        except KeyError as exc:
            raise BadRequest(f"missing field: {exc}") from exc

        amount = _parse_amount(body.get("amount"))

        try:
            req = WithdrawalService.create_request(
                agent_id=agent.id,
                amount=amount,
                payout_method=payout_method,
                payout_payload=payout_payload,
            )
            db.session.commit()
        except (
            WithdrawalAmountTooSmallError,
            InsufficientWithdrawableBalanceError,
            DuplicatePendingWithdrawalError,
            ValueError,
        ) as exc:
            db.session.rollback()
            raise BadRequest(str(exc)) from exc
        return _serialize(req), 201

    @setup_required
    @login_required
    @account_initialization_required
    @agent_required
    def get(self) -> dict:
        agent = g.current_agent
        page = max(1, int(request.args.get("page", 1)))
        limit = min(100, max(1, int(request.args.get("limit", 20))))
        offset = (page - 1) * limit

        rows = db.session.scalars(
            select(WithdrawalRequest)
            .where(WithdrawalRequest.agent_id == agent.id)
            .order_by(WithdrawalRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return {
            "data": [_serialize(r) for r in rows],
            "page": page,
            "limit": limit,
            "has_more": len(rows) == limit,
        }
