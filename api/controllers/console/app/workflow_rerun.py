"""HTTP endpoints for chatflow node-level rerun.

M1 — read-only "prepare" (POST .../rerun-from)
M2 — overrides CRUD: list / upsert / delete
M7 — streaming dispatch (lands later)

All endpoints are scoped to (app_id, message_id) and gated to
`AppMode.ADVANCED_CHAT` since rerun only makes sense in chatflow.
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
    RerunBusyError,
    RerunValidationError,
    WorkflowRerunService,
)

# RerunBusyError is consumed by the M7 streaming dispatcher when it actually
# holds the rerun lock; keep the import live so M7 doesn't have to revisit
# this file just to add it.
_BUSY_ERROR_FOR_M7 = RerunBusyError


def _serialize_override(row) -> dict:
    """Project a WorkflowRerunOverride row into a JSON-safe dict."""
    return {
        "id": str(row.id),
        "message_id": str(row.message_id),
        "workflow_run_id": str(row.workflow_run_id),
        "node_id": row.node_id,
        "kind": row.override_kind,
        "data": row.override_data,
        "created_by": str(row.created_by),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


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
                nid: sorted(outputs.keys())
                for nid, outputs in plan.ancestor_outputs.items()
            },
            "overrides_applied": plan.overrides_applied,
            # Non-blocking advisory: the UI greys out the rerun button when
            # a concurrent rerun already holds the lock on this message.
            "is_busy": WorkflowRerunService.is_rerun_in_progress(str(message_id)),
        }, 200


@console_ns.route("/apps/<uuid:app_id>/messages/<uuid:message_id>/rerun-overrides")
class ChatflowRerunOverridesApi(Resource):
    """List all overrides on a message; create/replace one node's override."""

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT])
    def get(self, app_model: App, message_id):
        try:
            rows = WorkflowRerunService.list_overrides(
                tenant_id=str(app_model.tenant_id),
                app_id=str(app_model.id),
                message_id=str(message_id),
            )
        except RerunValidationError as exc:
            return {"error": str(exc)}, 400

        return {
            "message_id": str(message_id),
            "overrides": [_serialize_override(r) for r in rows],
        }, 200

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT])
    def put(self, app_model: App, message_id):
        body = request.get_json(silent=True) or {}
        node_id = (body.get("node_id") or "").strip()
        kind = (body.get("kind") or "").strip()
        data = body.get("data")

        if not node_id:
            return {"error": "node_id is required"}, 400
        if not kind:
            return {"error": "kind is required ('input' or 'output')"}, 400
        if not isinstance(data, dict):
            return {"error": "data must be a JSON object"}, 400

        try:
            override = WorkflowRerunService.upsert_override(
                tenant_id=str(app_model.tenant_id),
                app_id=str(app_model.id),
                message_id=str(message_id),
                node_id=node_id,
                kind=kind,
                data=data,
                actor_id=str(current_user.id),
            )
        except RerunValidationError as exc:
            return {"error": str(exc)}, 400

        return _serialize_override(override), 200


@console_ns.route(
    "/apps/<uuid:app_id>/messages/<uuid:message_id>/rerun-overrides/<string:node_id>"
)
class ChatflowRerunOverrideItemApi(Resource):
    """Delete the override(s) on a specific node of a message."""

    @setup_required
    @login_required
    @account_initialization_required
    @get_app_model(mode=[AppMode.ADVANCED_CHAT])
    def delete(self, app_model: App, message_id, node_id):
        # `kind` is optional — when omitted we drop both input AND output
        # overrides for the node ("reset to original" behaviour).
        kind_arg = request.args.get("kind")
        kind = kind_arg.strip() if isinstance(kind_arg, str) else None
        if kind == "":
            kind = None

        try:
            deleted = WorkflowRerunService.delete_override(
                tenant_id=str(app_model.tenant_id),
                app_id=str(app_model.id),
                message_id=str(message_id),
                node_id=node_id,
                kind=kind,
            )
        except RerunValidationError as exc:
            return {"error": str(exc)}, 400

        return {"deleted": deleted}, 200
