"""Creator canvases endpoints (canvas-runtime CR2).

GET    /creator/canvases               — list current user's canvases (newest first)
POST   /creator/canvases               — save a successful workflow run as a named canvas
GET    /creator/canvases/<id>          — fetch a single canvas (owner-scoped)
PATCH  /creator/canvases/<id>          — rename
DELETE /creator/canvases/<id>          — delete

Owner + tenant isolation is enforced inside `UserCanvasService` so the
controller can't be tricked by spoofed body fields.
"""

from __future__ import annotations

from flask import request
from flask_restx import Resource
from sqlalchemy import select

from controllers.console import console_ns
from controllers.console.wraps import account_initialization_required, setup_required
from extensions.ext_database import db
from libs.login import current_account_with_tenant, login_required
from models.model import App
from services.user_canvas_service import (
    CanvasNotFoundError,
    CanvasQuotaExceededError,
    CanvasValidationError,
    UserCanvasService,
)


def _serialize(row) -> dict:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "app_id": str(row.app_id),
        "owner_id": str(row.owner_id),
        "title": row.title,
        "source_run_id": str(row.source_run_id),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _load_app_for_tenant(*, app_id: str, tenant_id: str) -> App | None:
    return db.session.execute(
        select(App).where(App.id == app_id).where(App.tenant_id == tenant_id)
    ).scalar_one_or_none()


@console_ns.route("/creator/canvases")
class CreatorCanvasesApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        current_user, current_tenant_id = current_account_with_tenant()
        app_id = request.args.get("app_id")
        rows = UserCanvasService.list_for_owner(
            tenant_id=current_tenant_id,
            owner_id=str(current_user.id),
            app_id=app_id,
        )
        return {"data": [_serialize(r) for r in rows], "total": len(rows)}, 200

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        current_user, current_tenant_id = current_account_with_tenant()
        body = request.get_json(silent=True) or {}
        app_id = (body.get("app_id") or "").strip()
        title = body.get("title") or ""
        source_run_id = (body.get("source_run_id") or "").strip()

        if not app_id:
            return {"error": "app_id is required"}, 400
        if not source_run_id:
            return {"error": "source_run_id is required"}, 400

        app = _load_app_for_tenant(app_id=app_id, tenant_id=current_tenant_id)
        if app is None:
            return {"error": "app not found"}, 404

        try:
            row = UserCanvasService.create(
                tenant_id=current_tenant_id,
                owner_id=str(current_user.id),
                app=app,
                title=title,
                source_run_id=source_run_id,
            )
        except CanvasValidationError as exc:
            return {"error": str(exc)}, 400
        except CanvasQuotaExceededError as exc:
            return {"error": str(exc), "code": "canvas_quota_exceeded"}, 409

        return _serialize(row), 201


@console_ns.route("/creator/canvases/<string:canvas_id>")
class CreatorCanvasItemApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, canvas_id):
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            row = UserCanvasService.get_for_owner(
                tenant_id=current_tenant_id,
                owner_id=str(current_user.id),
                canvas_id=canvas_id,
            )
        except CanvasNotFoundError:
            return {"error": "canvas not found"}, 404
        return _serialize(row), 200

    @setup_required
    @login_required
    @account_initialization_required
    def patch(self, canvas_id):
        current_user, current_tenant_id = current_account_with_tenant()
        body = request.get_json(silent=True) or {}
        title = body.get("title") or ""
        try:
            row = UserCanvasService.rename(
                tenant_id=current_tenant_id,
                owner_id=str(current_user.id),
                canvas_id=canvas_id,
                title=title,
            )
        except CanvasNotFoundError:
            return {"error": "canvas not found"}, 404
        except CanvasValidationError as exc:
            return {"error": str(exc)}, 400
        return _serialize(row), 200

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, canvas_id):
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            UserCanvasService.delete(
                tenant_id=current_tenant_id,
                owner_id=str(current_user.id),
                canvas_id=canvas_id,
            )
        except CanvasNotFoundError:
            return {"error": "canvas not found"}, 404
        return {"deleted": 1}, 200
