"""Publish-task REST endpoints.

Routes (all under /console/api):
- POST   /social-publish/tasks                  create a publish task
- GET    /social-publish/tasks                  list current tenant's tasks
- GET    /social-publish/tasks/<task_id>        status snapshot

Tenant isolation: same posture as the account routes; the service layer
re-resolves account_id and work_id through tenant-scoped queries before
trusting them.
"""

from __future__ import annotations

from flask import request
from flask_restx import Resource
from sqlalchemy.orm import sessionmaker

from configs import dify_config
from controllers.console import console_ns
from controllers.console.social_publish.error import (
    AccountExpiredHTTPError,
    AccountNotFoundHTTPError,
    FeatureDisabledHTTPError,
    PlatformUnsupportedHTTPError,
    SauApiHTTPError,
    SauUnreachableHTTPError,
    TaskAlreadyInFlightHTTPError,
    TaskInvalidPayloadHTTPError,
    TaskNotFoundHTTPError,
    TaskQuotaExceededHTTPError,
    VideoNotFoundHTTPError,
    VideoTooLargeHTTPError,
    WorkNotFoundHTTPError,
)
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from models.engine import db
from repositories.factory import DifyAPIRepositoryFactory
from services.errors.social_publish import (
    AccountExpiredError,
    AccountNotFoundError,
    FeatureDisabledError,
    PlatformUnsupportedError,
    SauApiError,
    SauUnreachableError,
    TaskAlreadyInFlightError,
    TaskInvalidPayloadError,
    TaskNotFoundError,
    TaskQuotaExceededError,
    VideoNotFoundError,
    VideoTooLargeError,
    WorkNotFoundError,
)
from services.sau_client import get_sau_client
from services.social_publish_task_service import (
    CreateTaskRequest,
    SocialPublishTaskService,
)


def _build_service() -> SocialPublishTaskService:
    if not (dify_config.SOCIAL_PUBLISH_ENABLED and dify_config.SAU_INTERNAL_TOKEN):
        raise FeatureDisabledError("publish-center is disabled")
    session_maker = sessionmaker(bind=db.engine, expire_on_commit=False)
    factory = DifyAPIRepositoryFactory
    try:
        sau_client = get_sau_client()
    except RuntimeError as exc:
        # ``get_sau_client`` raises RuntimeError on misconfig (token missing
        # at the lazy-init moment, < 16 chars, etc.). Surface as a typed
        # domain error so the controller maps it to 503 instead of 500.
        raise FeatureDisabledError(str(exc)) from exc
    return SocialPublishTaskService(
        task_repository=factory.create_social_publish_task_repository(session_maker=session_maker),
        account_repository=factory.create_social_publish_account_repository(session_maker=session_maker),
        sau_client=sau_client,
    )


def _to_http_error(exc: Exception) -> Exception:
    """Translate publish-task domain errors into HTTP exceptions.

    Listed in declaration order, not severity order — every concrete domain
    error class lives here so nothing falls through to a generic 500."""
    if isinstance(exc, FeatureDisabledError):
        return FeatureDisabledHTTPError()
    if isinstance(exc, PlatformUnsupportedError):
        return PlatformUnsupportedHTTPError()
    if isinstance(exc, AccountNotFoundError):
        return AccountNotFoundHTTPError()
    if isinstance(exc, AccountExpiredError):
        return AccountExpiredHTTPError()
    if isinstance(exc, WorkNotFoundError):
        return WorkNotFoundHTTPError()
    if isinstance(exc, TaskInvalidPayloadError):
        return TaskInvalidPayloadHTTPError()
    if isinstance(exc, TaskAlreadyInFlightError):
        return TaskAlreadyInFlightHTTPError()
    if isinstance(exc, TaskQuotaExceededError):
        return TaskQuotaExceededHTTPError()
    if isinstance(exc, TaskNotFoundError):
        return TaskNotFoundHTTPError()
    if isinstance(exc, VideoTooLargeError):
        return VideoTooLargeHTTPError()
    if isinstance(exc, VideoNotFoundError):
        return VideoNotFoundHTTPError()
    if isinstance(exc, SauUnreachableError):
        return SauUnreachableHTTPError()
    if isinstance(exc, SauApiError):
        return SauApiHTTPError()
    return exc


@console_ns.route("/social-publish/tasks")
class SocialPublishTasksApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self):
        _, current_tenant_id = current_account_with_tenant()
        account_id = request.args.get("account_id") or None
        status = request.args.get("status") or None
        try:
            limit = max(1, min(int(request.args.get("limit", 50)), 100))
        except (TypeError, ValueError):
            limit = 50
        try:
            service = _build_service()
            tasks = service.list_tasks(
                tenant_id=current_tenant_id,
                account_id=account_id,
                status=status,
                limit=limit,
            )
        except Exception as exc:
            raise _to_http_error(exc) from exc
        return {"data": [t.to_dict() for t in tasks]}

    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        current_user, current_tenant_id = current_account_with_tenant()
        body = request.get_json(silent=True) or {}
        req = CreateTaskRequest(
            account_id=str(body.get("account_id") or ""),
            work_id=body.get("work_id"),
            title=str(body.get("title") or ""),
            tags=list(body.get("tags") or []) or None,
            desc=body.get("desc"),
        )
        if not req.account_id:
            raise TaskInvalidPayloadHTTPError()
        try:
            service = _build_service()
            task = service.create_task(
                tenant_id=current_tenant_id,
                created_by=current_user.id,
                request=req,
            )
        except Exception as exc:
            raise _to_http_error(exc) from exc
        return {"task_id": task.id, "status": task.status}


@console_ns.route("/social-publish/tasks/<string:task_id>")
class SocialPublishTaskItemApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, task_id: str):
        _, current_tenant_id = current_account_with_tenant()
        try:
            service = _build_service()
            snapshot = service.get_task_status(
                task_id=task_id, tenant_id=current_tenant_id
            )
        except Exception as exc:
            raise _to_http_error(exc) from exc
        return {"task": snapshot.task, "result": snapshot.result}
