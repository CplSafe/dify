"""Agent console — invitees roster.

Routes:

- GET /agent/invitees           per-invitee rollup for the current agent

Note: ``PATCH /agent/invitees/<id>/note`` (per-invitee private note) is
deferred from Phase 2. Implementing it requires a new table to store
the agent-private note string, which Phase 0's migration didn't provision.
The list endpoint here exposes the data the dashboard table needs;
note-editing is tracked as a follow-up.
"""
from __future__ import annotations

from flask import g
from flask_restx import Resource

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    agent_required,
    setup_required,
)
from libs.login import login_required
from services.agent.agent_dashboard_service import AgentDashboardService


@console_ns.route("/agent/invitees")
class AgentInviteesApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @agent_required
    def get(self) -> dict:
        agent = g.current_agent
        rows = AgentDashboardService.invitees(agent.id)
        return {
            "data": [
                {
                    "invitee_account_id": r["invitee_account_id"],
                    "bound_at": r["bound_at"],
                    "month_consumption": str(r["month_consumption"]),
                    "total_rebate": str(r["total_rebate"]),
                }
                for r in rows
            ],
        }
