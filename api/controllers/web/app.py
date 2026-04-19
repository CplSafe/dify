import logging
from typing import Any, cast

from flask import request
from flask_restx import Resource
from pydantic import BaseModel, ConfigDict, Field
from werkzeug.exceptions import Unauthorized

from constants import HEADER_NAME_APP_CODE
from controllers.common import fields
from controllers.common.schema import register_schema_models
from core.app.app_config.common.parameters_mapping import get_parameters_from_feature_dict
from libs.passport import PassportService
from libs.token import extract_webapp_passport
from models.model import App, AppMode
from services.app_service import AppService
from services.enterprise.enterprise_service import EnterpriseService
from services.feature_service import FeatureService
from services.webapp_auth_service import WebAppAuthService

from . import web_ns
from .error import AppUnavailableError
from .wraps import WebApiResource

logger = logging.getLogger(__name__)


class AppAccessModeQuery(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    app_id: str | None = Field(default=None, alias="appId", description="Application ID")
    app_code: str | None = Field(default=None, alias="appCode", description="Application code")


register_schema_models(web_ns, AppAccessModeQuery)


@web_ns.route("/parameters")
class AppParameterApi(WebApiResource):
    """Resource for app variables."""

    @web_ns.doc(
        description="获取应用的参数配置，包括开场白、建议问题、用户输入表单字段等。"
                    "前端初始化聊天/工作流界面时调用，用于渲染输入表单和提示信息。",
        responses={
            200: "成功，返回参数配置",
            401: "未认证",
            403: "无访问权限",
            404: "应用不存在或配置缺失",
            500: "服务器内部错误",
        },
    )
    def get(self, app_model: App, end_user):
        """获取应用参数配置"""
        if app_model.mode in {AppMode.ADVANCED_CHAT, AppMode.WORKFLOW}:
            workflow = app_model.workflow
            if workflow is None:
                raise AppUnavailableError()

            features_dict: dict[str, Any] = workflow.features_dict
            user_input_form = workflow.user_input_form(to_old_structure=True)
        else:
            app_model_config = app_model.app_model_config
            if app_model_config is None:
                raise AppUnavailableError()

            features_dict = cast(dict[str, Any], app_model_config.to_dict())

            user_input_form = features_dict.get("user_input_form", [])

        parameters = get_parameters_from_feature_dict(features_dict=features_dict, user_input_form=user_input_form)
        return fields.Parameters.model_validate(parameters).model_dump(mode="json")


@web_ns.route("/meta")
class AppMeta(WebApiResource):
    @web_ns.doc(
        description="获取应用元数据，包括工具图标、工具描述等信息。"
                    "前端渲染 Agent 工具列表等场景时使用。",
        responses={
            200: "成功，返回元数据",
            401: "未认证",
            403: "无访问权限",
            404: "应用不存在",
            500: "服务器内部错误",
        },
    )
    def get(self, app_model: App, end_user):
        """获取应用元数据"""
        return AppService().get_app_meta(app_model)


@web_ns.route("/webapp/access-mode")
class AppAccessMode(Resource):
    @web_ns.doc(
        description="查询 Web 应用的访问模式（public / internal / external）。"
                    "前端据此判断是否需要引导用户登录。",
        params={
            "appId": {"description": "应用 ID", "type": "string", "required": False},
            "appCode": {"description": "应用 code", "type": "string", "required": False},
        },
        responses={
            200: "成功，返回 accessMode",
            400: "参数错误",
            500: "服务器内部错误",
        },
    )
    def get(self):
        """查询 Web 应用访问模式"""
        raw_args = request.args.to_dict()
        args = AppAccessModeQuery.model_validate(raw_args)

        features = FeatureService.get_system_features()
        if not features.webapp_auth.enabled:
            return {"accessMode": "public"}

        app_id = args.app_id
        if args.app_code:
            app_id = AppService.get_app_id_by_code(args.app_code)

        if not app_id:
            raise ValueError("appId or appCode must be provided")

        res = EnterpriseService.WebAppAuth.get_app_access_mode_by_id(app_id)

        return {"accessMode": res.access_mode}


@web_ns.route("/webapp/permission")
class AppWebAuthPermission(Resource):
    @web_ns.doc(
        description="检查当前用户是否有权限访问指定 Web 应用。"
                    "企业版权限校验场景使用，公开应用始终返回 true。",
        params={"appId": {"description": "应用 ID", "type": "string", "required": True}},
        responses={
            200: "成功，返回 result（布尔值）",
            400: "参数错误",
            401: "未授权",
            500: "服务器内部错误",
        },
    )
    def get(self):
        """检查用户对 Web 应用的访问权限"""
        user_id = "visitor"
        app_code = request.headers.get(HEADER_NAME_APP_CODE)
        app_id = request.args.get("appId")
        if not app_id or not app_code:
            raise ValueError("appId must be provided")

        require_permission_check = WebAppAuthService.is_app_require_permission_check(app_id=app_id)
        if not require_permission_check:
            return {"result": True}

        try:
            tk = extract_webapp_passport(app_code, request)
            if not tk:
                raise Unauthorized("Access token is missing.")
            decoded = PassportService().verify(tk)
            user_id = decoded.get("user_id", "visitor")
        except Unauthorized:
            raise
        except Exception:
            logger.exception("Unexpected error during auth verification")
            raise

        features = FeatureService.get_system_features()
        if not features.webapp_auth.enabled:
            return {"result": True}

        res = True
        if WebAppAuthService.is_app_require_permission_check(app_id=app_id):
            res = EnterpriseService.WebAppAuth.is_user_allowed_to_access_webapp(str(user_id), app_id)
        return {"result": res}
