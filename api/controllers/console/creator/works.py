"""Creator works endpoints.

GET  /creator/works           — list current user's works
POST /creator/works           — create a new work entry
POST /creator/works/<id>/publish — update share_status
DELETE /creator/works/<id>    — delete a work
"""

from flask import request
from flask_restx import Resource
from sqlalchemy import select

from controllers.console import console_ns
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from models.creator import CreatorWork, CreatorWorkShareStatus
from models.engine import db


@console_ns.route("/creator/works")
class CreatorWorksApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """List current user's creator works."""
        current_user, current_tenant_id = current_account_with_tenant()

        limit = min(int(request.args.get("limit", 20)), 100)
        offset = int(request.args.get("offset", 0))

        base_query = select(CreatorWork).where(CreatorWork.account_id == current_user.id)
        total = db.session.scalar(
            select(db.func.count()).select_from(base_query.subquery())
        ) or 0
        works = list(
            db.session.scalars(
                base_query.order_by(CreatorWork.created_at.desc()).limit(limit).offset(offset)
            ).all()
        )

        return {
            "data": [w.to_dict() for w in works],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """Create a new creator work entry."""
        current_user, current_tenant_id = current_account_with_tenant()

        payload = request.get_json() or {}
        title = payload.get("title", "Untitled")
        workflow_run_id = payload.get("workflow_run_id")
        app_id = payload.get("app_id")
        file_key = payload.get("file_key")
        file_type = payload.get("file_type", "video")
        output_data = payload.get("output_data")

        if workflow_run_id:
            existing_work = db.session.scalar(
                select(CreatorWork).where(
                    CreatorWork.account_id == current_user.id,
                    CreatorWork.workflow_run_id == workflow_run_id,
                )
            )
            if existing_work:
                return existing_work.to_dict(), 200

        work = CreatorWork(
            account_id=current_user.id,
            tenant_id=current_tenant_id,
            workflow_run_id=workflow_run_id,
            app_id=app_id,
            title=title,
            file_key=file_key,
            file_type=file_type,
            output_data=output_data,
        )
        db.session.add(work)
        db.session.commit()

        return work.to_dict(), 201


@console_ns.route("/creator/works/<string:work_id>")
class CreatorWorkItemApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, work_id: str):
        """Delete a creator work."""
        current_user, _ = current_account_with_tenant()
        work = db.session.scalar(
            select(CreatorWork).where(
                CreatorWork.id == work_id,
                CreatorWork.account_id == current_user.id,
            )
        )
        if not work:
            from werkzeug.exceptions import NotFound
            raise NotFound("Work not found")

        db.session.delete(work)
        db.session.commit()
        return {"result": "success"}


@console_ns.route("/creator/works/<string:work_id>/publish")
class CreatorWorkPublishApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def post(self, work_id: str):
        """Update the share status of a creator work (publish to social platform)."""
        current_user, _ = current_account_with_tenant()
        work = db.session.scalar(
            select(CreatorWork).where(
                CreatorWork.id == work_id,
                CreatorWork.account_id == current_user.id,
            )
        )
        if not work:
            from werkzeug.exceptions import NotFound
            raise NotFound("Work not found")

        payload = request.get_json() or {}
        platform = payload.get("platform", "")

        status_map = {
            "tiktok": CreatorWorkShareStatus.PUBLISHED_TIKTOK.value,
            "xhs": CreatorWorkShareStatus.PUBLISHED_XHS.value,
        }
        new_status = status_map.get(platform)
        if not new_status:
            from werkzeug.exceptions import BadRequest
            raise BadRequest(f"Unsupported platform: {platform}. Use 'tiktok' or 'xhs'.")

        work.share_status = new_status
        db.session.add(work)
        db.session.commit()

        return work.to_dict()
