import logging
from typing import Any

from graphon.graph_engine.manager import GraphEngineManager
from graphon.model_runtime.errors.invoke import InvokeError
from pydantic import BaseModel, Field
from werkzeug.exceptions import InternalServerError

from controllers.common.errors import raise_workflow_budget_http_error
from controllers.common.schema import register_schema_models
from controllers.web import web_ns
from controllers.web.error import (
    CompletionRequestError,
    NotWorkflowAppError,
    ProviderModelCurrentlyNotSupportError,
    ProviderNotInitializeError,
    ProviderQuotaExceededError,
)
from controllers.web.error import InvokeRateLimitError as InvokeRateLimitHttpError
from controllers.web.wraps import WebApiResource
from core.app.apps.base_app_queue_manager import AppQueueManager
from core.app.entities.app_invoke_entities import InvokeFrom
from core.errors.error import (
    ModelCurrentlyNotSupportError,
    ProviderTokenNotInitError,
    QuotaExceededError,
)
from extensions.ext_redis import redis_client
from libs import helper
from models.model import App, AppMode, EndUser
from services.app_generate_service import AppGenerateService
from services.errors.llm import InvokeRateLimitError
from services.wallet.exceptions import WorkflowBudgetExceeded


class WorkflowRunPayload(BaseModel):
    inputs: dict[str, Any] = Field(description="Input variables for the workflow")
    files: list[dict[str, Any]] | None = Field(default=None, description="Files to be processed by the workflow")


logger = logging.getLogger(__name__)

register_schema_models(web_ns, WorkflowRunPayload)


@web_ns.route("/workflows/run")
class WorkflowRunApi(WebApiResource):
    @web_ns.expect(web_ns.models[WorkflowRunPayload.__name__])
    @web_ns.doc(
        description="执行工作流应用，传入输入变量和文件。"
                    "以 SSE 流式方式返回工作流运行过程中的各节点事件。"
                    "仅适用于 workflow 模式应用。",
        responses={
            200: "成功，返回工作流执行事件流",
            400: "请求错误",
            401: "未认证",
            403: "无访问权限",
            404: "应用不存在",
            500: "服务器内部错误",
        },
    )
    def post(self, app_model: App, end_user: EndUser):
        """执行工作流"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode != AppMode.WORKFLOW:
            raise NotWorkflowAppError()

        payload = WorkflowRunPayload.model_validate(web_ns.payload or {})
        args = payload.model_dump(exclude_none=True)

        try:
            response = AppGenerateService.generate(
                app_model=app_model, user=end_user, args=args, invoke_from=InvokeFrom.WEB_APP, streaming=True
            )

            return helper.compact_generate_response(response)
        except ProviderTokenNotInitError as ex:
            raise ProviderNotInitializeError(ex.description)
        except QuotaExceededError:
            raise ProviderQuotaExceededError()
        except ModelCurrentlyNotSupportError:
            raise ProviderModelCurrentlyNotSupportError()
        except InvokeError as e:
            raise CompletionRequestError(e.description)
        except WorkflowBudgetExceeded as ex:
            raise_workflow_budget_http_error(ex.code)
        except InvokeRateLimitError as ex:
            raise InvokeRateLimitHttpError(ex.description)
        except ValueError as e:
            raise e
        except Exception:
            logger.exception("internal server error.")
            raise InternalServerError()


@web_ns.route("/workflows/tasks/<string:task_id>/stop")
class WorkflowTaskStopApi(WebApiResource):
    @web_ns.doc(
        description="停止正在运行的工作流任务。task_id 从流式事件的 workflow_started 事件中获取。",
        params={
            "task_id": {"description": "要停止的任务 ID", "type": "string", "required": True},
        },
        responses={
            200: "停止成功",
            401: "未认证",
            403: "无访问权限",
            404: "任务不存在",
        },
    )
    def post(self, app_model: App, end_user: EndUser, task_id: str):
        """停止工作流任务"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode != AppMode.WORKFLOW:
            raise NotWorkflowAppError()

        # Stop using both mechanisms for backward compatibility
        # Legacy stop flag mechanism (without user check)
        AppQueueManager.set_stop_flag_no_user_check(task_id)

        # New graph engine command channel mechanism
        GraphEngineManager(redis_client).send_stop_command(task_id)

        return {"result": "success"}
