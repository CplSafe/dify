"""
Web App Human Input Form APIs.
"""

import json
import logging
from datetime import datetime

from flask import Response, request
from flask_restx import Resource, reqparse
from sqlalchemy import select
from werkzeug.exceptions import Forbidden

from configs import dify_config
from controllers.web import web_ns
from controllers.web.error import NotFoundError, WebFormRateLimitExceededError
from controllers.web.site import serialize_app_site_payload
from extensions.ext_database import db
from libs.helper import RateLimiter, extract_remote_ip
from models.account import TenantStatus
from models.model import App, Site
from services.human_input_service import Form, FormNotFoundError, HumanInputService

logger = logging.getLogger(__name__)

_FORM_SUBMIT_RATE_LIMITER = RateLimiter(
    prefix="web_form_submit_rate_limit",
    max_attempts=dify_config.WEB_FORM_SUBMIT_RATE_LIMIT_MAX_ATTEMPTS,
    time_window=dify_config.WEB_FORM_SUBMIT_RATE_LIMIT_WINDOW_SECONDS,
)
_FORM_ACCESS_RATE_LIMITER = RateLimiter(
    prefix="web_form_access_rate_limit",
    max_attempts=dify_config.WEB_FORM_SUBMIT_RATE_LIMIT_MAX_ATTEMPTS,
    time_window=dify_config.WEB_FORM_SUBMIT_RATE_LIMIT_WINDOW_SECONDS,
)


def _stringify_default_values(values: dict[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        if value is None:
            result[key] = ""
        elif isinstance(value, (dict, list)):
            result[key] = json.dumps(value, ensure_ascii=False)
        else:
            result[key] = str(value)
    return result


def _to_timestamp(value: datetime) -> int:
    return int(value.timestamp())


def _jsonify_form_definition(form: Form, site_payload: dict | None = None) -> Response:
    """Return the form payload (optionally with site) as a JSON response."""
    definition_payload = form.get_definition().model_dump()
    payload = {
        "form_content": definition_payload["rendered_content"],
        "inputs": definition_payload["inputs"],
        "resolved_default_values": _stringify_default_values(definition_payload["default_values"]),
        "user_actions": definition_payload["user_actions"],
        "expiration_time": _to_timestamp(form.expiration_time),
    }
    if site_payload is not None:
        payload["site"] = site_payload
    return Response(json.dumps(payload, ensure_ascii=False), mimetype="application/json")


@web_ns.route("/form/human_input/<string:form_token>")
class HumanInputFormApi(Resource):
    """API for getting and submitting human input forms via the web app."""

    # NOTE(QuantumGhost): this endpoint is unauthenticated on purpose for now.

    @web_ns.doc(
        description="通过表单令牌获取人工输入表单定义。"
                    "此接口故意设计为公开接口（无需认证），供外部用户填写工作流人工输入表单。"
                    "有访问频率限制（IP 级别）。",
        params={"form_token": {"description": "表单访问令牌", "type": "string", "required": True}},
        responses={
            200: "成功，返回表单定义（含输入字段和操作按钮）",
            404: "表单不存在或已失效",
            429: "访问频率超限",
        },
    )
    # def get(self, _app_model: App, _end_user: EndUser, form_token: str):
    def get(self, form_token: str):
        """获取人工输入表单定义"""
        ip_address = extract_remote_ip(request)
        if _FORM_ACCESS_RATE_LIMITER.is_rate_limited(ip_address):
            raise WebFormRateLimitExceededError()
        _FORM_ACCESS_RATE_LIMITER.increment_rate_limit(ip_address)

        service = HumanInputService(db.engine)
        # TODO(QuantumGhost): forbid submision for form tokens
        # that are only for console.
        form = service.get_form_by_token(form_token)

        if form is None:
            raise NotFoundError("Form not found")

        service.ensure_form_active(form)
        app_model, site = _get_app_site_from_form(form)

        return _jsonify_form_definition(form, site_payload=serialize_app_site_payload(app_model, site, None))

    @web_ns.doc(
        description="提交人工输入表单。"
                    "用户填写表单后，系统将触发对应的工作流步骤继续执行。"
                    "有提交频率限制（IP 级别）。",
        params={"form_token": {"description": "表单访问令牌", "type": "string", "required": True}},
        responses={
            200: "提交成功",
            404: "表单不存在",
            429: "提交频率超限",
        },
    )
    # def post(self, _app_model: App, _end_user: EndUser, form_token: str):
    def post(self, form_token: str):
        """提交人工输入表单"""
        parser = reqparse.RequestParser()
        parser.add_argument("inputs", type=dict, required=True, location="json")
        parser.add_argument("action", type=str, required=True, location="json")
        args = parser.parse_args()

        ip_address = extract_remote_ip(request)
        if _FORM_SUBMIT_RATE_LIMITER.is_rate_limited(ip_address):
            raise WebFormRateLimitExceededError()
        _FORM_SUBMIT_RATE_LIMITER.increment_rate_limit(ip_address)

        service = HumanInputService(db.engine)
        form = service.get_form_by_token(form_token)
        if form is None:
            raise NotFoundError("Form not found")

        if (recipient_type := form.recipient_type) is None:
            logger.warning("Recipient type is None for form, form_id=%", form.id)
            raise AssertionError("Recipient type is None")

        try:
            service.submit_form_by_token(
                recipient_type=recipient_type,
                form_token=form_token,
                selected_action_id=args["action"],
                form_data=args["inputs"],
                submission_end_user_id=None,
                # submission_end_user_id=_end_user.id,
            )
        except FormNotFoundError:
            raise NotFoundError("Form not found")

        return {}, 200


def _get_app_site_from_form(form: Form) -> tuple[App, Site]:
    """Resolve App/Site for the form's app and validate tenant status."""
    app_model = db.session.get(App, form.app_id)
    if app_model is None or app_model.tenant_id != form.tenant_id:
        raise NotFoundError("Form not found")

    site = db.session.scalar(select(Site).where(Site.app_id == app_model.id).limit(1))
    if site is None:
        raise Forbidden()

    if app_model.tenant and app_model.tenant.status == TenantStatus.ARCHIVE:
        raise Forbidden()

    return app_model, site
