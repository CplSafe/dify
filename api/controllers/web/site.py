from typing import cast

from flask_restx import fields, marshal, marshal_with
from sqlalchemy import select
from werkzeug.exceptions import Forbidden

from configs import dify_config
from controllers.web import web_ns
from controllers.web.wraps import WebApiResource
from extensions.ext_database import db
from libs.helper import AppIconUrlField, SignedFileUrlField
from models.account import TenantStatus
from models.model import App, Site
from services.feature_service import FeatureService

_model_config_model = web_ns.model(
    "AppModelConfig",
    {
        "opening_statement": fields.String,
        "suggested_questions": fields.Raw(attribute="suggested_questions_list"),
        "suggested_questions_after_answer": fields.Raw(attribute="suggested_questions_after_answer_dict"),
        "more_like_this": fields.Raw(attribute="more_like_this_dict"),
        "model": fields.Raw(attribute="model_dict"),
        "user_input_form": fields.Raw(attribute="user_input_form_list"),
        "pre_prompt": fields.String,
    },
)

_site_model = web_ns.model(
    "AppSite",
    {
        "title": fields.String,
        "chat_color_theme": fields.String,
        "chat_color_theme_inverted": fields.Boolean,
        "chat_page_background_color": fields.String,
        "icon_type": fields.String,
        "icon": fields.String,
        "icon_background": fields.String,
        "icon_url": AppIconUrlField,
        "description": fields.String,
        "copyright": fields.String,
        "privacy_policy": fields.String,
        "default_user_avatar_url": SignedFileUrlField,
        "default_user_avatar_file_id": fields.String(attribute="default_user_avatar_url"),
        "custom_disclaimer": fields.String,
        "enable_homepage": fields.Boolean,
        "default_language": fields.String,
        "prompt_public": fields.Boolean,
        "show_workflow_steps": fields.Boolean,
        "show_answer_disclaimer": fields.Boolean,
        "use_icon_as_answer_icon": fields.Boolean,
    },
)

_app_model = web_ns.model(
    "AppInfo",
    {
        "app_id": fields.String,
        "end_user_id": fields.String,
        "enable_site": fields.Boolean,
        "site": fields.Nested(_site_model),
        "model_config": fields.Nested(_model_config_model, allow_null=True),
        "plan": fields.String,
        "can_replace_logo": fields.Boolean,
        "custom_config": fields.Raw(attribute="custom_config"),
    },
)


@web_ns.route("/site")
class AppSiteApi(WebApiResource):
    """Resource for app sites."""

    model_config_fields = _model_config_model
    site_fields = _site_model
    app_fields = _app_model

    @web_ns.doc(
        description="获取 Web 应用站点信息，包括标题、图标、颜色主题、版权声明等配置。"
                    "前端初始化时调用此接口以渲染站点外观。",
        responses={
            200: "成功，返回站点及应用配置",
            401: "未认证，缺少或无效的访问令牌",
            403: "应用未开放站点访问，或租户已归档",
            404: "应用不存在",
        },
    )
    @marshal_with(app_fields)
    def get(self, app_model, end_user):
        """获取 Web 应用站点信息"""
        # get site
        site = db.session.scalar(select(Site).where(Site.app_id == app_model.id).limit(1))

        if not site:
            raise Forbidden()

        if app_model.tenant.status == TenantStatus.ARCHIVE:
            raise Forbidden()

        can_replace_logo = FeatureService.get_features(app_model.tenant_id).can_replace_logo

        return AppSiteInfo(app_model.tenant, app_model, site, end_user.id, can_replace_logo)


class AppSiteInfo:
    """Class to store site information."""

    def __init__(self, tenant, app, site, end_user, can_replace_logo):
        """Initialize AppSiteInfo instance."""
        self.app_id = app.id
        self.end_user_id = end_user
        self.enable_site = app.enable_site
        self.site = site
        self.model_config = None
        self.plan = tenant.plan
        self.can_replace_logo = can_replace_logo

        if can_replace_logo:
            base_url = dify_config.FILES_URL
            remove_webapp_brand = tenant.custom_config_dict.get("remove_webapp_brand", False)
            replace_webapp_logo = (
                f"{base_url}/files/workspaces/{tenant.id}/webapp-logo"
                if tenant.custom_config_dict.get("replace_webapp_logo")
                else None
            )
            self.custom_config = {
                "remove_webapp_brand": remove_webapp_brand,
                "replace_webapp_logo": replace_webapp_logo,
            }


def serialize_site(site: Site) -> dict:
    """Serialize Site model using the same schema as AppSiteApi."""
    return cast(dict, marshal(site, AppSiteApi.site_fields))


def serialize_app_site_payload(app_model: App, site: Site, end_user_id: str | None) -> dict:
    can_replace_logo = FeatureService.get_features(app_model.tenant_id).can_replace_logo
    app_site_info = AppSiteInfo(app_model.tenant, app_model, site, end_user_id, can_replace_logo)
    return cast(dict, marshal(app_site_info, AppSiteApi.app_fields))
