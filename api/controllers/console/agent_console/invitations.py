"""Agent console — invitation code management.

Routes:

- POST /agent/invitations          mint a fresh code (long-lived, reusable)
- GET  /agent/invitations          list this agent's anchor codes
"""
from __future__ import annotations

from flask import g
from flask_restx import Resource
from sqlalchemy import and_, select

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    agent_required,
    setup_required,
)
from extensions.ext_database import db
from libs.login import login_required
from models.creator import AccountInvitation
from services.agent.agent_invitation_service import AgentInvitationService


@console_ns.route("/agent/invitations")
class AgentInvitationsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @agent_required
    def post(self) -> tuple[dict, int]:
        agent = g.current_agent
        code = AgentInvitationService.generate_invitation_code(agent.id)
        db.session.commit()
        return {"invite_code": code}, 201

    @setup_required
    @login_required
    @account_initialization_required
    @agent_required
    def get(self) -> dict:
        """List anchor rows for this agent (one anchor per minted code).

        Each anchor row has invitee_account_id IS NULL and status='pending'.
        Subsequent binds insert new rows with the same code + actual invitee.
        """
        agent = g.current_agent
        anchors = db.session.scalars(
            select(AccountInvitation)
            .where(
                and_(
                    AccountInvitation.agent_id == agent.id,
                    AccountInvitation.invitee_account_id.is_(None),
                )
            )
            .order_by(AccountInvitation.created_at.desc())
        ).all()
        return {
            "data": [
                {
                    "invite_code": a.invite_code,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in anchors
            ],
        }
