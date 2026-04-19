"""Publish-task REST endpoints.

Routes (all under /console/api):
- POST   /social-publish/tasks                  create a publish task
- POST   /social-publish/tasks/batch            create up to N tasks in one call
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
from controllers.console.social_publish.models import (
    batch_create_task_req,
    batch_create_task_resp,
    create_task_req,
    create_task_resp,
    task_list_resp,
    task_status_resp,
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
    BatchCreateTaskRequest,
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
    @console_ns.doc(
        description="获取当前成员的发布任务列表（成员级隔离）。",
        params={
            "account_id": "可选，按账号 ID 过滤",
            "status": "可选，按状态过滤：pending / queued / running / success / failed",
            "limit": "可选，返回条数上限，默认 50，最大 100",
        },
        responses={200: ("成功", task_list_resp)},
    )
    @console_ns.marshal_with(task_list_resp)
    def get(self):
        """获取当前成员的发布任务列表"""
        # P8: per-member — list only the current member's tasks.
        current_user, current_tenant_id = current_account_with_tenant()
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
                user_id=current_user.id,
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
    @console_ns.doc(
        description="创建单个发布任务，将视频发布到指定社交账号。",
        responses={
            200: ("成功", create_task_resp),
            400: "入参缺失或格式错误",
            404: "账号不存在或不属于当前成员",
            409: "该账号已有进行中的发布任务（单飞限制）",
            429: "当前租户待处理任务数超出配额",
        },
    )
    @console_ns.expect(create_task_req, validate=False)
    @console_ns.marshal_with(create_task_resp)
    def post(self):
        """创建发布任务"""
        current_user, current_tenant_id = current_account_with_tenant()
        body = request.get_json(silent=True) or {}
        platform_payload = body.get("platform_payload")
        if platform_payload is not None and not isinstance(platform_payload, dict):
            raise TaskInvalidPayloadHTTPError()
        req = CreateTaskRequest(
            account_id=str(body.get("account_id") or ""),
            work_id=body.get("work_id"),
            title=str(body.get("title") or ""),
            tags=list(body.get("tags") or []) or None,
            desc=body.get("desc"),
            platform_payload=platform_payload,
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


@console_ns.route("/social-publish/tasks/batch")
class SocialPublishTasksBatchApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="批量创建发布任务，将同一视频同时发布到多个社交账号。"
                    "响应始终为 200，每个目标账号单独返回成功/失败结果，"
                    "部分失败不影响其他账号的任务创建。",
        responses={200: ("成功，含每个目标的结果", batch_create_task_resp)},
    )
    @console_ns.expect(batch_create_task_req, validate=False)
    @console_ns.marshal_with(batch_create_task_resp)
    def post(self):
        """批量创建发布任务"""
        current_user, current_tenant_id = current_account_with_tenant()
        body = request.get_json(silent=True) or {}
        raw_targets = body.get("targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            raise TaskInvalidPayloadHTTPError()
        targets: list[BatchCreateTaskRequest] = []
        for raw in raw_targets:
            if not isinstance(raw, dict):
                raise TaskInvalidPayloadHTTPError()
            account_id = str(raw.get("account_id") or "")
            if not account_id:
                raise TaskInvalidPayloadHTTPError()
            platform_payload = raw.get("platform_payload")
            if platform_payload is not None and not isinstance(platform_payload, dict):
                raise TaskInvalidPayloadHTTPError()
            targets.append(
                BatchCreateTaskRequest(
                    account_id=account_id,
                    platform_payload=platform_payload,
                )
            )
        try:
            service = _build_service()
            results = service.create_tasks_batch(
                tenant_id=current_tenant_id,
                created_by=current_user.id,
                work_id=body.get("work_id"),
                title=str(body.get("title") or ""),
                tags=list(body.get("tags") or []) or None,
                desc=body.get("desc"),
                targets=targets,
            )
        except Exception as exc:
            raise _to_http_error(exc) from exc
        return {
            "results": [
                {
                    "account_id": r.account_id,
                    "success": r.success,
                    "task_id": r.task_id,
                    "error_code": r.error_code,
                    "error_message": r.error_message,
                }
                for r in results
            ]
        }


@console_ns.route("/social-publish/tasks/<string:task_id>")
class SocialPublishTaskItemApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="查询单个发布任务的状态快照。前端建议每 3 秒轮询一次，"
                    "直到 task.status 为 success / failed。"
                    "若返回 challenge_session_id 说明 SAU worker 触发了 SMS 验证，"
                    "需打开短信验证弹窗（/social-publish/tasks/{task_id} 的 challenge 流程）。",
        responses={
            200: ("成功", task_status_resp),
            404: "任务不存在或不属于当前成员",
        },
    )
    @console_ns.marshal_with(task_status_resp)
    def get(self, task_id: str):
        """查询发布任务状态"""
        # P8: per-member — only the task's creator can poll its status.
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            service = _build_service()
            snapshot = service.get_task_status(
                task_id=task_id,
                tenant_id=current_tenant_id,
                user_id=current_user.id,
            )
        except Exception as exc:
            raise _to_http_error(exc) from exc
        return {
            "task": snapshot.task,
            "result": snapshot.result,
            # P7: when sau worker is mid-flow waiting for SMS verification,
            # this lets the FE pivot to the SmsChallengePanel without waiting
            # for the task to terminate.
            "challenge_session_id": snapshot.challenge_session_id,
        }
