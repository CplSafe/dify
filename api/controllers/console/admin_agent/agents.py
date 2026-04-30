"""Sysadmin endpoints for managing agent records.

Routes (all under /console/api/admin/agents):

- POST   /admin/agents                  open a new agent
- GET    /admin/agents                  list agents (paginated, filtered)
- GET    /admin/agents/<agent_id>       agent detail
- PATCH  /admin/agents/<agent_id>       update whitelist fields (rebate_rate / notes / etc.)
- POST   /admin/agents/<agent_id>/suspend     mark agent as suspended

All endpoints require ``user.is_system_admin`` — non-admin users get 403
from ``system_admin_required`` decorator.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

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
from models.agent import Agent
from services.agent.agent_service import AgentService
from services.errors.agent import (
    AgentAccountAlreadyExistsError,
    AgentNotFoundError,
)


def _parse_decimal(raw: Any, field: str) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError) as exc:
        raise BadRequest(f"invalid {field}: {raw!r}") from exc


def _parse_date(raw: Any, field: str) -> date | None:
    if raw is None or raw == "":
        return None
    try:
        return date.fromisoformat(str(raw))
    except (ValueError, TypeError) as exc:
        raise BadRequest(f"invalid {field}: {raw!r}") from exc


@console_ns.route("/admin/agents")
class AdminAgentsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def post(self) -> tuple[dict, int]:
        body = request.get_json(silent=True) or {}
        try:
            account_id = body["account_id"]
            name = body["name"]
        except KeyError as exc:
            raise BadRequest(f"missing field: {exc}") from exc

        try:
            agent = AgentService.create_agent(
                account_id=account_id,
                name=name,
                created_by=current_user.id,
                rebate_rate=_parse_decimal(body.get("rebate_rate"), "rebate_rate"),
                level=body.get("level"),
                region_province=body.get("region_province"),
                region_city=body.get("region_city"),
                contact_phone=body.get("contact_phone"),
                notes=body.get("notes"),
                signed_at=_parse_date(body.get("signed_at"), "signed_at"),
                expires_at=_parse_date(body.get("expires_at"), "expires_at"),
            )
            db.session.commit()
        except AgentAccountAlreadyExistsError as exc:
            db.session.rollback()
            raise BadRequest(str(exc)) from exc
        return agent.to_dict(), 201

    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def get(self) -> dict:
        """Paginated agent list, optionally filtered by status."""
        page = max(1, int(request.args.get("page", 1)))
        limit = min(100, max(1, int(request.args.get("limit", 20))))
        status = request.args.get("status")  # 'active' / 'suspended' / None

        stmt = select(Agent).order_by(Agent.created_at.desc())
        if status:
            stmt = stmt.where(Agent.status == status)

        offset = (page - 1) * limit
        rows = db.session.scalars(stmt.offset(offset).limit(limit)).all()
        return {
            "data": [a.to_dict() for a in rows],
            "page": page,
            "limit": limit,
            "has_more": len(rows) == limit,
        }


@console_ns.route("/admin/agents/<string:agent_id>")
class AdminAgentDetailApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def get(self, agent_id: str) -> dict:
        try:
            return AgentService.get_by_id(agent_id).to_dict()
        except AgentNotFoundError as exc:
            raise NotFound(str(exc)) from exc

    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def patch(self, agent_id: str) -> dict:
        body = request.get_json(silent=True) or {}
        # Whitelist of patchable fields with type coercion
        fields: dict[str, Any] = {}
        for key in ("name", "level", "region_province", "region_city", "contact_phone", "notes"):
            if key in body:
                fields[key] = body[key]
        if "rebate_rate" in body:
            fields["rebate_rate"] = _parse_decimal(body["rebate_rate"], "rebate_rate")
        if "signed_at" in body:
            fields["signed_at"] = _parse_date(body["signed_at"], "signed_at")
        if "expires_at" in body:
            fields["expires_at"] = _parse_date(body["expires_at"], "expires_at")

        try:
            agent = AgentService.update_agent(agent_id, **fields)
            db.session.commit()
        except AgentNotFoundError as exc:
            db.session.rollback()
            raise NotFound(str(exc)) from exc
        except ValueError as exc:
            db.session.rollback()
            raise BadRequest(str(exc)) from exc
        return agent.to_dict()


@console_ns.route("/admin/agents/<string:agent_id>/suspend")
class AdminAgentSuspendApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @system_admin_required
    def post(self, agent_id: str) -> dict:
        try:
            agent = AgentService.suspend_agent(agent_id)
            db.session.commit()
        except AgentNotFoundError as exc:
            db.session.rollback()
            raise NotFound(str(exc)) from exc
        return agent.to_dict()
