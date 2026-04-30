"""Sysadmin endpoints for reviewing rebind requests.

Routes (under /console/api):

- GET   /admin/rebind-requests                      list (paginated, status filter)
- POST  /admin/rebind-requests/<request_id>/approve approve a pending rebind
- POST  /admin/rebind-requests/<request_id>/reject  reject a pending rebind
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
from models.agent import RebindRequest
from services.agent.rebind_service import RebindService
from services.errors.agent import (
    AgentNotFoundError,
    RebindRequestNotFoundError,
)


def _serialize(req: RebindRequest) -> dict:
    return {
        "id": req.id,
        "account_id": req.account_id,
        "from_agent_id": req.from_agent_id,
        "to_agent_id": req.to_agent_id,
        "status": req.status,
        "reviewer_id": req.reviewer_id,
        "review_note": req.review_note,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
    }


@console_ns.route("/admin/rebind-requests")
class AdminRebindRequestsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def get(self) -> dict:
        page = max(1, int(request.args.get("page", 1)))
        limit = min(100, max(1, int(request.args.get("limit", 20))))
        status = request.args.get("status")

        stmt = select(RebindRequest).order_by(RebindRequest.created_at.desc())
        if status:
            stmt = stmt.where(RebindRequest.status == status)

        offset = (page - 1) * limit
        rows = db.session.scalars(stmt.offset(offset).limit(limit)).all()
        return {
            "data": [_serialize(r) for r in rows],
            "page": page,
            "limit": limit,
            "has_more": len(rows) == limit,
        }


@console_ns.route("/admin/rebind-requests/<string:request_id>/approve")
class AdminRebindApproveApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def post(self, request_id: str) -> dict:
        body = request.get_json(silent=True) or {}
        try:
            req = RebindService.approve(
                request_id, reviewer_id=current_user.id, note=body.get("note"),
            )
            db.session.commit()
        except RebindRequestNotFoundError as exc:
            db.session.rollback()
            raise NotFound(str(exc)) from exc
        except AgentNotFoundError as exc:
            db.session.rollback()
            raise BadRequest(str(exc)) from exc
        return _serialize(req)


@console_ns.route("/admin/rebind-requests/<string:request_id>/reject")
class AdminRebindRejectApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def post(self, request_id: str) -> dict:
        body = request.get_json(silent=True) or {}
        try:
            req = RebindService.reject(
                request_id, reviewer_id=current_user.id, note=body.get("note"),
            )
            db.session.commit()
        except RebindRequestNotFoundError as exc:
            db.session.rollback()
            raise NotFound(str(exc)) from exc
        return _serialize(req)
