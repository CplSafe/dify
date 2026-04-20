"""Creator task endpoints.

POST   /creator/tasks           — 创建任务（启动 chatflow 时调用）
GET    /creator/tasks           — 查询用户的任务列表（进行中 + 已完成）
GET    /creator/tasks/<id>      — 查询单个任务详情
PATCH  /creator/tasks/<id>      — 更新任务状态/标题（支持乐观锁）
DELETE /creator/tasks/<id>      — 删除任务
"""

from datetime import UTC, datetime

from flask import request
from flask_restx import Resource, fields
from werkzeug.exceptions import BadRequest

from controllers.console import console_ns
from controllers.console.wraps import account_initialization_required, setup_required
from libs.login import current_account_with_tenant, login_required
from models.creator_task import CreatorTaskStatus
from services.creator_task_service import CreatorTaskService

VALID_STATUSES = {s.value for s in CreatorTaskStatus}
MAX_TITLE_LENGTH = 200

# ---------------------------------------------------------------------------
# Model 定义
# ---------------------------------------------------------------------------

_task_item = console_ns.model(
    "CreatorTaskItem",
    {
        "id": fields.String(description="任务 ID"),
        "title": fields.String(description="任务标题"),
        "status": fields.String(
            description="任务状态，取值：" + " / ".join(sorted(VALID_STATUSES))
        ),
        "app_id": fields.String(description="关联的应用 ID"),
        "installed_app_id": fields.String(description="关联的已安装应用 ID"),
        "conversation_id": fields.String(description="关联的对话 ID，可为空"),
        "workflow_run_id": fields.String(description="关联的工作流运行 ID，可为空"),
        "created_at": fields.String(description="创建时间 ISO8601"),
        "updated_at": fields.String(description="最后更新时间 ISO8601"),
    },
)

_task_list_resp = console_ns.model(
    "CreatorTaskListResp",
    {
        "tasks": fields.List(fields.Nested(_task_item), description="任务列表"),
        "total": fields.Integer(description="任务总数"),
        "in_progress_count": fields.Integer(description="进行中任务数"),
    },
)

_create_task_req = console_ns.model(
    "CreatorTaskCreateReq",
    {
        "app_id": fields.String(
            required=True,
            description="关联的应用 ID",
            example="app-abc123",
        ),
        "installed_app_id": fields.String(
            required=True,
            description="关联的已安装应用 ID",
            example="installed-xyz789",
        ),
        "title": fields.String(
            required=False,
            description="任务标题，最长 200 字符",
            example="生成旅行视频",
        ),
        "conversation_id": fields.String(
            required=False,
            description="关联的对话 ID",
            example="conv-000111",
        ),
        "workflow_run_id": fields.String(
            required=False,
            description="关联的工作流运行 ID",
            example="run-222333",
        ),
    },
)

_patch_task_req = console_ns.model(
    "CreatorTaskPatchReq",
    {
        "status": fields.String(
            required=False,
            description="新状态值，取值：" + " / ".join(sorted(VALID_STATUSES)),
            example="completed",
        ),
        "title": fields.String(
            required=False,
            description="新任务标题，最长 200 字符",
            example="生成旅行视频（已修改）",
        ),
        "last_updated_at": fields.String(
            required=False,
            description="乐观锁时间戳（ISO 8601），传入时若任务在此时间后被修改则返回 409",
            example="2024-01-01T12:00:00+00:00",
        ),
    },
)

# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@console_ns.route("/creator/tasks")
class CreatorTaskListApi(Resource):

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="查询当前用户的创作者任务列表，包含进行中和已完成的任务。",
        responses={
            200: ("成功", _task_list_resp),
            401: "未登录",
        },
    )
    @console_ns.marshal_with(_task_list_resp)
    def get(self):
        """查询当前用户的创作者任务列表"""
        current_user, _ = current_account_with_tenant()
        return CreatorTaskService.list_tasks(current_user.id)

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="创建一个新的创作者任务。app_id 和 installed_app_id 为必填项，"
                    "创建成功后返回任务对象（状态码 201）。",
        responses={
            201: ("创建成功", _task_item),
            400: "缺少必填参数",
            401: "未登录",
        },
    )
    @console_ns.expect(_create_task_req, validate=False)
    def post(self):
        """创建新的创作者任务"""
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
    @console_ns.doc(
        description="查询单个创作者任务的详细信息。任务不存在或不属于当前用户时返回 404。",
        responses={
            200: ("成功", _task_item),
            401: "未登录",
            404: "任务不存在",
        },
    )
    @console_ns.marshal_with(_task_item)
    def get(self, task_id: str):
        """查询单个创作者任务详情"""
        current_user, _ = current_account_with_tenant()
        task = CreatorTaskService.get_task(task_id, current_user.id)
        return task.to_dict()

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="更新任务状态和/或标题。至少需提供 status 或 title 之一。"
                    "传入 last_updated_at（ISO 8601）可启用乐观锁冲突检测，"
                    "若任务在该时间之后被修改，则返回 409。",
        responses={
            200: ("更新成功", _task_item),
            400: "参数错误（缺少字段或状态值非法）",
            401: "未登录",
            404: "任务不存在",
            409: "乐观锁冲突，任务已被其他操作修改",
        },
    )
    @console_ns.expect(_patch_task_req, validate=False)
    @console_ns.marshal_with(_task_item)
    def patch(self, task_id: str):
        """更新任务状态和/或标题（支持乐观锁）"""
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
    @console_ns.doc(
        description="删除指定的创作者任务。只有任务所有者可删除，删除成功返回空体 204。",
        responses={
            204: "删除成功",
            401: "未登录",
            404: "任务不存在",
        },
    )
    def delete(self, task_id: str):
        """删除创作者任务"""
        current_user, _ = current_account_with_tenant()
        CreatorTaskService.delete_task(task_id, current_user.id)
        return {}, 204
