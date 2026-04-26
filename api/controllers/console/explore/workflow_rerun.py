"""Creator-facing chatflow rerun endpoints (CR10).

Mirrors `console.app.workflow_rerun` but mounted under
`/installed-apps/<installed_app_id>/...` so end-users (creators using a
chatflow that was published to their workspace via installed-apps) can
edit a completed node and rerun the chatflow without needing
console-app permissions.

The heavy lifting — validation, override CRUD, paused vs terminated
dispatch routing — lives in `WorkflowRerunService`. These endpoints are
thin adapters that resolve `installed_app -> app_model` and forward.
"""

from __future__ import annotations

from flask import request

from controllers.console import console_ns
from controllers.console.app.error import AppUnavailableError
from controllers.console.explore.wraps import InstalledAppResource
from libs.login import current_user
from models.model import AppMode, InstalledApp
from services.workflow_rerun_service import (
    RerunBusyError,
    RerunPausedMismatchError,
    RerunValidationError,
    WorkflowRerunService,
)


def _serialize_override(row) -> dict:
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


def _require_chatflow_app(installed_app: InstalledApp):
    app_model = installed_app.app
    if app_model is None or app_model.mode != AppMode.ADVANCED_CHAT:
        raise AppUnavailableError()
    return app_model


@console_ns.route(
    "/installed-apps/<uuid:installed_app_id>/messages/<uuid:message_id>/rerun-from",
    endpoint="installed_app_rerun_prepare",
)
class InstalledAppRerunPrepareApi(InstalledAppResource):
    """Build a rerun plan for inspection (does not execute)."""

    def post(self, installed_app: InstalledApp, message_id):
        app_model = _require_chatflow_app(installed_app)
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
            "is_busy": WorkflowRerunService.is_rerun_in_progress(str(message_id)),
        }, 200


@console_ns.route(
    "/installed-apps/<uuid:installed_app_id>/messages/<uuid:message_id>/rerun-overrides",
    endpoint="installed_app_rerun_overrides",
)
class InstalledAppRerunOverridesApi(InstalledAppResource):
    """List + upsert rerun overrides for a message."""

    def get(self, installed_app: InstalledApp, message_id):
        app_model = _require_chatflow_app(installed_app)
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

    def put(self, installed_app: InstalledApp, message_id):
        app_model = _require_chatflow_app(installed_app)
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
    "/installed-apps/<uuid:installed_app_id>/messages/<uuid:message_id>/rerun-from/dispatch",
    endpoint="installed_app_rerun_dispatch",
)
class InstalledAppRerunDispatchApi(InstalledAppResource):
    """Trigger the rerun for a chatflow message.

    The service routes paused vs terminated runs to the correct backend:
    paused → existing celery resume task, terminated → new
    `rerun_app_execution` task that builds a fresh run rooted at the
    chosen node.
    """

    def post(self, installed_app: InstalledApp, message_id):
        app_model = _require_chatflow_app(installed_app)
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

        try:
            workflow_run_id = WorkflowRerunService.dispatch(
                plan=plan, actor_id=str(current_user.id)
            )
        except RerunBusyError as exc:
            return {"error": str(exc), "code": "rerun_busy"}, 409
        except RerunPausedMismatchError as exc:
            return {"error": str(exc), "code": "rerun_paused_mismatch"}, 400
        except RerunValidationError as exc:
            return {"error": str(exc)}, 400

        return {"status": "started", "workflow_run_id": workflow_run_id}, 200


@console_ns.route(
    "/installed-apps/<uuid:installed_app_id>/messages/<uuid:message_id>/rerun-overrides/<string:node_id>",
    endpoint="installed_app_rerun_override_item",
)
class InstalledAppRerunOverrideItemApi(InstalledAppResource):
    """Delete the override(s) on a node — kind optional ('reset to original')."""

    def delete(self, installed_app: InstalledApp, message_id, node_id):
        app_model = _require_chatflow_app(installed_app)
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
