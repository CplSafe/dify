"""Customer-facing bind endpoints.

Routes (under /console/api):

- GET  /agent/bind/preview              show agent profile for a code (NO LOGIN required)
- POST /agent/bind/confirm              authenticated bind (after registration / login)
- POST /agent/bind/rebind-request       authenticated rebind request

Design note (§5.2-5.4):
- ``preview`` is intentionally public — customers must see the agent
  identity BEFORE they register / log in (to make an informed decision).
  We expose only display fields (name / level / region) — never internal
  IDs, contact_phone, notes, expires_at, or rebate_rate.
- ``confirm`` requires login because bind needs the invitee's account_id.
- ``rebind-request`` likewise requires login.
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
)
from extensions.ext_database import db
from libs.login import login_required
from models.agent import Agent, AgentStatus
from models.creator import AccountInvitation
from services.agent.agent_invitation_service import AgentInvitationService
from services.agent.rebind_service import RebindService
from services.errors.agent import (
    AgentNotFoundError,
    AgentSuspendedError,
    AlreadyBoundError,
    DuplicatePendingRebindError,
    InvalidAgentInvitationCodeError,
    RebindCooldownActiveError,
    SelfBindError,
)

_PUBLIC_AGENT_FIELDS = (
    "name", "level", "region_province", "region_city",
)


def _public_agent_view(agent: Agent) -> dict:
    """Whitelisted display fields safe to expose to unauthenticated users."""
    return {key: getattr(agent, key) for key in _PUBLIC_AGENT_FIELDS}


@console_ns.route("/agent/bind/preview")
class AgentBindPreviewApi(Resource):
    """Public endpoint: show agent profile for a code, no login required."""

    @setup_required
    def get(self) -> dict:
        code = (request.args.get("code") or "").strip()
        if not code:
            raise BadRequest("code is required")

        anchor = db.session.scalar(
            select(AccountInvitation).where(
                AccountInvitation.invite_code == code,
                AccountInvitation.invitee_account_id.is_(None),
            )
        )
        if anchor is None:
            raise NotFound("invitation code not found")

        agent = db.session.scalar(select(Agent).where(Agent.id == anchor.agent_id))
        if agent is None or agent.status != AgentStatus.ACTIVE.value:
            raise NotFound("invitation is no longer active")

        return _public_agent_view(agent)


@console_ns.route("/agent/bind/confirm")
class AgentBindConfirmApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self) -> dict:
        body = request.get_json(silent=True) or {}
        code = (body.get("code") or "").strip()
        if not code:
            raise BadRequest("code is required")

        try:
            agent = AgentInvitationService.bind(
                invite_code=code, invitee_account_id=current_user.id,
            )
            db.session.commit()
        except InvalidAgentInvitationCodeError as exc:
            db.session.rollback()
            raise NotFound(str(exc)) from exc
        except (AgentSuspendedError, SelfBindError) as exc:
            db.session.rollback()
            raise BadRequest(str(exc)) from exc
        except AlreadyBoundError as exc:
            db.session.rollback()
            # Special case: caller should switch to the rebind flow.
            # 409 Conflict is the right HTTP semantics, but werkzeug's
            # Conflict isn't always exposed; we use BadRequest with a
            # discriminating error_code in the body so the frontend can
            # branch.
            raise BadRequest({"error_code": "already_bound", "message": str(exc)}) from exc

        return {"agent": _public_agent_view(agent)}


@console_ns.route("/agent/bind/rebind-request")
class AgentRebindRequestApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self) -> tuple[dict, int]:
        body = request.get_json(silent=True) or {}
        try:
            from_agent_id = body["from_agent_id"]
            to_agent_id = body["to_agent_id"]
        except KeyError as exc:
            raise BadRequest(f"missing field: {exc}") from exc

        try:
            req = RebindService.create_request(
                account_id=current_user.id,
                from_agent_id=from_agent_id,
                to_agent_id=to_agent_id,
            )
            db.session.commit()
        except AgentNotFoundError as exc:
            db.session.rollback()
            raise NotFound(str(exc)) from exc
        except (DuplicatePendingRebindError, RebindCooldownActiveError) as exc:
            db.session.rollback()
            raise BadRequest(str(exc)) from exc

        return {"id": req.id, "status": req.status}, 201
