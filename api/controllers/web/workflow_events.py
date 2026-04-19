"""
Web App Workflow Resume APIs.
"""

import json
from collections.abc import Generator

from flask import Response, request
from sqlalchemy.orm import sessionmaker

from controllers.web import api, web_ns
from controllers.web.error import InvalidArgumentError, NotFoundError
from controllers.web.wraps import WebApiResource
from core.app.apps.advanced_chat.app_generator import AdvancedChatAppGenerator
from core.app.apps.base_app_generator import BaseAppGenerator
from core.app.apps.common.workflow_response_converter import WorkflowResponseConverter
from core.app.apps.message_generator import MessageGenerator
from core.app.apps.workflow.app_generator import WorkflowAppGenerator
from extensions.ext_database import db
from models.enums import CreatorUserRole
from models.model import App, AppMode, EndUser
from repositories.factory import DifyAPIRepositoryFactory
from services.workflow_event_snapshot_service import build_workflow_event_stream


class WorkflowEventsApi(WebApiResource):
    """API for getting workflow execution events after resume."""

    @web_ns.doc(
        description="获取工作流执行事件流（SSE）。"
                    "用于恢复/重连场景：当前端与流式事件连接中断后，"
                    "可通过此接口重新订阅并获取任务已产生的所有事件。"
                    "若任务已完成则立即返回结束事件；否则从 Redis 读取实时事件流。",
        params={
            "task_id": {"description": "工作流任务 ID（即 workflow_run_id）", "type": "string"},
            "include_state_snapshot": {
                "description": "是否包含节点状态快照，默认 false",
                "type": "boolean",
                "required": False,
            },
        },
        responses={
            200: "成功，返回 SSE 事件流（text/event-stream）",
            401: "未认证",
            404: "任务不存在或无权访问",
        },
    )
    def get(self, app_model: App, end_user: EndUser, task_id: str):
        """获取工作流执行事件流"""
        workflow_run_id = task_id
        session_maker = sessionmaker(db.engine)
        repo = DifyAPIRepositoryFactory.create_api_workflow_run_repository(session_maker)
        workflow_run = repo.get_workflow_run_by_id_and_tenant_id(
            tenant_id=app_model.tenant_id,
            run_id=workflow_run_id,
        )

        if workflow_run is None:
            raise NotFoundError(f"WorkflowRun not found, id={workflow_run_id}")

        if workflow_run.app_id != app_model.id:
            raise NotFoundError(f"WorkflowRun not found, id={workflow_run_id}")

        if workflow_run.created_by_role != CreatorUserRole.END_USER:
            raise NotFoundError(f"WorkflowRun not created by end user, id={workflow_run_id}")

        if workflow_run.created_by != end_user.id:
            raise NotFoundError(f"WorkflowRun not created by the current end user, id={workflow_run_id}")

        if workflow_run.finished_at is not None:
            response = WorkflowResponseConverter.workflow_run_result_to_finish_response(
                task_id=workflow_run.id,
                workflow_run=workflow_run,
                creator_user=end_user,
            )

            payload = response.model_dump(mode="json")
            payload["event"] = response.event.value

            def _generate_finished_events() -> Generator[str, None, None]:
                yield f"data: {json.dumps(payload)}\n\n"

            event_generator = _generate_finished_events
        else:
            app_mode = AppMode.value_of(app_model.mode)
            msg_generator = MessageGenerator()
            generator: BaseAppGenerator
            if app_mode == AppMode.ADVANCED_CHAT:
                generator = AdvancedChatAppGenerator()
            elif app_mode == AppMode.WORKFLOW:
                generator = WorkflowAppGenerator()
            else:
                raise InvalidArgumentError(f"cannot subscribe to workflow run, workflow_run_id={workflow_run.id}")

            include_state_snapshot = request.args.get("include_state_snapshot", "false").lower() == "true"

            def _generate_stream_events():
                if include_state_snapshot:
                    return generator.convert_to_event_stream(
                        build_workflow_event_stream(
                            app_mode=app_mode,
                            workflow_run=workflow_run,
                            tenant_id=app_model.tenant_id,
                            app_id=app_model.id,
                            session_maker=session_maker,
                        )
                    )
                return generator.convert_to_event_stream(
                    msg_generator.retrieve_events(app_mode, workflow_run.id),
                )

            event_generator = _generate_stream_events

        return Response(
            event_generator(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )


# Register the APIs
api.add_resource(WorkflowEventsApi, "/workflow/<string:task_id>/events")
