"""Creator task endpoints.

POST   /creator/tasks           — create a task when a chatflow is launched
GET    /creator/tasks           — list user's tasks (in-progress + completed)
GET    /creator/tasks/<id>      — get a single task
PATCH  /creator/tasks/<id>      — update task status (with optimistic lock)
"""

from datetime import UTC, datetime

from flask import request
from flask_restx import Resource
from werkzeug.exceptions import BadRequest

from controllers.console import console_ns
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from models.creator_task import CreatorTaskStatus
from services.creator_task_service import CreatorTaskService

VALID_STATUSES = {s.value for s in CreatorTaskStatus}
MAX_TITLE_LENGTH = 200


@console_ns.route("/creator/tasks")
class CreatorTaskListApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        """List current user's creator tasks."""
        current_user, _ = current_account_with_tenant()
        return CreatorTaskService.list_tasks(current_user.id)

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """Create a new creator task."""
        current_user, current_tenant_id = current_account_with_tenant()

        payload = request.get_json() or {}
        app_id = payload.get("app_id")
        installed_app_id = payload.get("installed_app_id")

        if not app_id or not installed_app_id:
            raise BadRequest("app_id and installed_app_id are required.")

        title = str(payload.get("title", ""))[:MAX_TITLE_LENGTH] or None

        task = CreatorTaskService.create_task(
            account_id=current_user.id,
            tenant_id=current_tenant_id,
            app_id=app_id,
            installed_app_id=installed_app_id,
            conversation_id=payload.get("conversation_id"),
            workflow_run_id=payload.get("workflow_run_id"),
            title=title,
        )
        return task.to_dict(), 201


@console_ns.route("/creator/tasks/<string:task_id>")
class CreatorTaskItemApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    def get(self, task_id: str):
        """Get a single creator task."""
        current_user, _ = current_account_with_tenant()
        task = CreatorTaskService.get_task(task_id, current_user.id)
        return task.to_dict()

    @setup_required
    @login_required
    @account_initialization_required
    def patch(self, task_id: str):
        """Update task status and/or title.

        Send last_updated_at (ISO 8601) to enable conflict detection on status changes.
        Returns 409 if the task was modified since last_updated_at.
        At least one of 'status' or 'title' must be provided.
        """
        current_user, _ = current_account_with_tenant()

        payload = request.get_json() or {}
        new_status = payload.get("status")
        new_title = payload.get("title")

        if new_status is None and new_title is None:
            raise BadRequest("At least one of 'status' or 'title' must be provided.")

        if new_status is not None and new_status not in VALID_STATUSES:
            raise BadRequest(f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")

        if new_title is not None and not isinstance(new_title, str):
            raise BadRequest("title must be a string.")

        last_updated_at: datetime | None = None
        raw_ts = payload.get("last_updated_at")
        if raw_ts:
            try:
                last_updated_at = datetime.fromisoformat(raw_ts).replace(tzinfo=UTC)
            except ValueError:
                raise BadRequest("last_updated_at must be a valid ISO 8601 datetime string.")

        task = CreatorTaskService.update_task(
            task_id=task_id,
            account_id=current_user.id,
            new_status=new_status,
            new_title=str(new_title)[:MAX_TITLE_LENGTH] if new_title is not None else None,
            last_updated_at=last_updated_at,
        )
        return task.to_dict()

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, task_id: str):
        """Delete a creator task."""
        current_user, _ = current_account_with_tenant()
        CreatorTaskService.delete_task(task_id, current_user.id)
        return {}, 204
