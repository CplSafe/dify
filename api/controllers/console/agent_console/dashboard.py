"""Agent console — dashboard endpoint.

Routes (under /console/api):

- GET /agent/dashboard          wallet summary + 7-day trend (default)

Wraps the read-only ``AgentDashboardService`` aggregations.
"""
from __future__ import annotations

from decimal import Decimal

from flask import g, request
from flask_restx import Resource

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    agent_required,
    setup_required,
)
from libs.login import login_required
from services.agent.agent_dashboard_service import AgentDashboardService


def _stringify_decimals(d: dict) -> dict:
    """Decimal → str so JSON precision survives."""
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}


@console_ns.route("/agent/dashboard")
class AgentDashboardApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @agent_required
    def get(self) -> dict:
        agent = g.current_agent
        days = max(1, min(30, int(request.args.get("days", 7))))

        wallet = _stringify_decimals(AgentDashboardService.wallet_summary(agent.id))
        trend_rows = AgentDashboardService.daily_consumption(agent.id, days=days)
        trend = [
            {"date": r["date"], "consumption": str(r["consumption"])}
            for r in trend_rows
        ]
        return {"wallet": wallet, "trend": trend}
