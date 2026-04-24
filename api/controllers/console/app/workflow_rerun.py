"""HTTP endpoints for chatflow node-level rerun (M1).

Currently exposes a single read-only "prepare" endpoint so backend logic
can be exercised end-to-end via curl before the editing API (M2) and the
streaming dispatcher (M7) land.

POST /apps/<app_id>/messages/<message_id>/rerun-from
Body: { "node_id": "<workflow node id>", "kind": "input" | "output" }
"""

from __future__ import annotations

from flask import request
from flask_restx import Resource

from controllers.console import console_ns
from controllers.console.app.wraps import get_app_model
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_user, login_required
from models import App
from models.model import AppMode
from services.workflow_rerun_service import (
    RerunValidationError,
    WorkflowRerunService,
)


@console_ns.route("/apps/<uuid:app_id>/messages/<uuid:message_id>/rerun-from")
class ChatflowRerunPrepareApi(Resource):
    """Build a rerun plan for a chatflow message — does not execute yet."""

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT])
    def post(self, app_model: App, message_id):
        body = request.get_json(silent=True) or {}
        node_id = (body.get("node_id") or "").strip()
        kind = (body.get("kind") or "input").strip()

        if not node_id:
            return {"error": "node_id is required"}, 400

        try:
            plan = WorkflowRerunService.prepare(
                tenant_id=str(app_model.tenant_id),
                app_id=str(app_model.id),
                message_id=str(message_id),
                rewind_node_id=node_id,
                rewind_kind=kind,
            )
        except RerunValidationError as exc:
            return {"error": str(exc)}, 400

        return {
            "source_message_id": plan.source_message_id,
            "source_run_id": plan.source_run_id,
            "workflow_id": plan.workflow_id,
            "rewind_node_id": plan.rewind_node_id,
            "rewind_kind": plan.rewind_kind,
            "start_node_id": plan.start_node_id,
            "ancestor_node_ids": sorted(plan.ancestor_outputs.keys()),
            "ancestor_output_keys": {
                nid: sorted(outputs.keys()) for nid, outputs in plan.ancestor_outputs.items()
            },
            "overrides_applied": plan.overrides_applied,
        }, 200


# Touch current_user import so linters don't strip it; will be used in M2/M7
# when we record the actor on each override and rerun audit row.
_ = current_user
