"""Social-publish account REST endpoints.

Routes (all under /console/api):

- GET    /social-publish/accounts                     list current tenant's accounts
- POST   /social-publish/accounts/auth/start          start a sau scan-to-auth session
- GET    /social-publish/accounts/auth/status/<sid>   poll auth-session status
- DELETE /social-publish/accounts/<id>                delete an account

Tenant isolation is enforced both by the controller (via
``current_account_with_tenant``) and the service layer (which constrains
every repository query by ``tenant_id``).
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
    SessionExpiredHTTPError,
    TenantMismatchHTTPError,
)
from controllers.console.social_publish.models import (
    account_list_resp,
    auth_start_req,
    auth_start_resp,
    auth_status_resp,
    challenge_action_resp,
    challenge_state_resp,
    challenge_submit_req,
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
    SessionExpiredError,
    TenantMismatchError,
)
from services.sau_client import get_sau_client
from services.social_publish_service import SocialPublishService


def _build_service() -> SocialPublishService:
    """Per-request service factory.

    Kept as a function (not a Flask-extension singleton) so unit tests can
    monkey-patch ``get_sau_client`` and the repository factory independently
    without touching the controller surface.

    The combined gate (master flag AND token) mirrors what
    ``FeatureService.get_system_features().social_publish_enabled`` exposes to
    the frontend, so the FE never sees the feature as enabled while the BE
    would 500 on a missing token.
    """
    if not (dify_config.SOCIAL_PUBLISH_ENABLED and dify_config.SAU_INTERNAL_TOKEN):
        raise FeatureDisabledError("publish-center is disabled")

    session_maker = sessionmaker(bind=db.engine, expire_on_commit=False)
    repo = DifyAPIRepositoryFactory.create_social_publish_account_repository(session_maker=session_maker)
    try:
        sau_client = get_sau_client()
    except RuntimeError as exc:
        # ``get_sau_client`` raises RuntimeError on misconfig (token < 16
        # chars, etc.). Surface as a typed domain error so the controller
        # maps it to 503 instead of 500.
        raise FeatureDisabledError(str(exc)) from exc
    return SocialPublishService(repository=repo, sau_client=sau_client)


def _to_http_error(exc: Exception) -> Exception:
    """Translate domain errors to Werkzeug HTTP exceptions.

    Every staged ``services.errors.social_publish`` class must appear here so
    nothing falls through to a generic 500 once it starts being raised.
    """
    if isinstance(exc, FeatureDisabledError):
        return FeatureDisabledHTTPError()
    if isinstance(exc, PlatformUnsupportedError):
        return PlatformUnsupportedHTTPError()
    if isinstance(exc, AccountNotFoundError):
        return AccountNotFoundHTTPError()
    if isinstance(exc, TenantMismatchError):
        return TenantMismatchHTTPError()
    if isinstance(exc, AccountExpiredError):
        return AccountExpiredHTTPError()
    if isinstance(exc, SessionExpiredError):
        return SessionExpiredHTTPError()
    if isinstance(exc, SauUnreachableError):
        return SauUnreachableHTTPError()
    if isinstance(exc, SauApiError):
        return SauApiHTTPError()
    return exc


@console_ns.route("/social-publish/accounts")
class SocialPublishAccountsListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="获取当前成员已绑定的社交账号列表（成员级隔离，只能看到自己绑定的账号）",
        params={"platform": "可选，按平台过滤，取值 douyin / xhs"},
        responses={
            200: ("成功", account_list_resp),
            400: "功能未启用或请求参数错误",
            401: "未登录",
        },
    )
    @console_ns.marshal_with(account_list_resp)
    def get(self):
        """获取当前成员已绑定的社交账号列表"""
        current_user, current_tenant_id = current_account_with_tenant()
        platform = request.args.get("platform") or None
        try:
            service = _build_service()
            accounts = service.list_accounts(
                tenant_id=current_tenant_id,
                user_id=current_user.id,
                platform=platform,
            )
        except Exception as exc:
            raise _to_http_error(exc) from exc

        return {"data": [a.to_dict() for a in accounts]}


@console_ns.route("/social-publish/accounts/auth/start")
class SocialPublishAuthStartApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="发起社交账号授权，返回二维码图片（base64）。"
                    "用户扫码后轮询 /auth/status/{session_id} 获取结果。"
                    "重新授权时传入 account_id。",
        responses={
            200: ("成功，返回 session_id 和二维码", auth_start_resp),
            422: "platform 参数缺失或不支持",
            503: "SAU 服务不可用",
        },
    )
    @console_ns.expect(auth_start_req, validate=False)
    @console_ns.marshal_with(auth_start_resp)
    def post(self):
        """发起社交账号扫码授权"""
        current_user, current_tenant_id = current_account_with_tenant()
        payload = request.get_json(silent=True) or {}
        platform = payload.get("platform")
        account_id = payload.get("account_id")

        if not platform:
            raise PlatformUnsupportedHTTPError()

        try:
            service = _build_service()
            result = service.start_auth(
                tenant_id=current_tenant_id,
                platform=platform,
                account_id=account_id,
                created_by=current_user.id,
            )
        except Exception as exc:
            raise _to_http_error(exc) from exc

        return {
            "session_id": result.session_id,
            "qr_image_base64": result.qr_image_base64,
            "expires_in": result.expires_in,
        }


@console_ns.route("/social-publish/accounts/auth/status/<string:session_id>")
class SocialPublishAuthStatusApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="轮询扫码授权会话状态。前端建议每 2 秒轮询一次，"
                    "直到 status 为 success / expired / failed。"
                    "若返回 challenge_session_id 说明触发了 SMS 二次验证，需切换到短信验证弹窗。",
        responses={
            200: ("成功", auth_status_resp),
            404: "session_id 不存在或已过期",
        },
    )
    @console_ns.marshal_with(auth_status_resp)
    def get(self, session_id: str):
        """轮询扫码授权会话状态"""
        _, current_tenant_id = current_account_with_tenant()
        try:
            service = _build_service()
            result = service.get_auth_status(session_id=session_id, tenant_id=current_tenant_id)
        except Exception as exc:
            raise _to_http_error(exc) from exc

        return {
            "status": result.status,
            "account": result.account,
            "message": result.message,
            "challenge_session_id": result.challenge_session_id,
        }


@console_ns.route("/social-publish/accounts/<string:account_id>")
class SocialPublishAccountItemApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="解绑社交账号。只有绑定该账号的成员才能删除（成员级隔离）。",
        responses={
            200: "删除成功",
            404: "账号不存在或不属于当前成员",
        },
    )
    def delete(self, account_id: str):
        """解绑社交账号"""
        current_user, current_tenant_id = current_account_with_tenant()
        try:
            service = _build_service()
            service.delete_account(
                account_id=account_id,
                tenant_id=current_tenant_id,
                user_id=current_user.id,
            )
        except Exception as exc:
            raise _to_http_error(exc) from exc

        return {"result": "success"}


# ---------- P7: SMS challenge relay ----------
#
# These three routes are pass-through wrappers around sau's
# /challenge/{id}/* endpoints. We do NOT enforce challenge_session ↔
# tenant binding here because:
#   1. The session id is server-generated by sau (uuid4); it's
#      effectively unguessable without first triggering an SMS challenge
#      on a specific tenant's account.
#   2. The sau side already 404s any unknown id and 409s any terminal id.
#   3. Adding a tenant-binding lookup here would require persisting
#      challenge_session_id ↔ tenant in dify, which doubles the storage
#      surface for a 5-minute Redis-only object.
# Worth revisiting if/when challenge_session_id becomes guessable.


@console_ns.route(
    "/social-publish/accounts/auth/challenge/<string:challenge_session_id>"
)
class SocialPublishAuthChallengeApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="查询 SMS 二次验证会话状态。前端每 2 秒轮询一次，"
                    "直到 status 为 completed / aborted。",
        responses={200: ("成功", challenge_state_resp), 404: "会话不存在"},
    )
    @console_ns.marshal_with(challenge_state_resp)
    def get(self, challenge_session_id: str):
        """查询 SMS 验证会话状态"""
        try:
            service = _build_service()
            data = service.sau_client_get_challenge(session_id=challenge_session_id)
        except Exception as exc:
            raise _to_http_error(exc) from exc
        return data


@console_ns.route(
    "/social-publish/accounts/auth/challenge/<string:challenge_session_id>/trigger-sms"
)
class SocialPublishAuthChallengeTriggerSmsApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="触发平台发送短信验证码。对应用户点击「获取验证码」按钮，"
                    "后端会在 Chromium 页面自动点击对应按钮。无请求体。",
        responses={200: ("成功", challenge_action_resp), 404: "会话不存在"},
    )
    @console_ns.marshal_with(challenge_action_resp)
    def post(self, challenge_session_id: str):
        """触发平台发送短信验证码"""
        try:
            service = _build_service()
            data = service.sau_client_trigger_sms(session_id=challenge_session_id)
        except Exception as exc:
            raise _to_http_error(exc) from exc
        return data


@console_ns.route(
    "/social-publish/accounts/auth/challenge/<string:challenge_session_id>/submit-code"
)
class SocialPublishAuthChallengeSubmitCodeApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="提交用户输入的短信验证码。后端自动填入 Chromium 页面并点击验证。"
                    "若平台返回验证码错误，ok=false 且 detail 说明原因，需用户重新输入。",
        responses={200: ("成功", challenge_action_resp), 400: "验证码格式错误（非纯数字或长度不对）"},
    )
    @console_ns.expect(challenge_submit_req, validate=False)
    @console_ns.marshal_with(challenge_action_resp)
    def post(self, challenge_session_id: str):
        """提交短信验证码"""
        body = request.get_json(silent=True) or {}
        code = str(body.get("code") or "").strip()
        if not (code.isdigit() and 4 <= len(code) <= 8):
            from controllers.console.social_publish.error import (
                TaskInvalidPayloadHTTPError,
            )
            raise TaskInvalidPayloadHTTPError()
        try:
            service = _build_service()
            data = service.sau_client_submit_code(
                session_id=challenge_session_id, code=code,
            )
        except Exception as exc:
            raise _to_http_error(exc) from exc
        return data


@console_ns.route(
    "/social-publish/accounts/auth/challenge/<string:challenge_session_id>/abort"
)
class SocialPublishAuthChallengeAbortApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.doc(
        description="用户主动取消 SMS 验证，中止当前会话。无请求体。",
        responses={200: ("成功", challenge_action_resp), 404: "会话不存在"},
    )
    @console_ns.marshal_with(challenge_action_resp)
    def post(self, challenge_session_id: str):
        """取消 SMS 验证会话"""
        try:
            service = _build_service()
            data = service.sau_client_abort(session_id=challenge_session_id)
        except Exception as exc:
            raise _to_http_error(exc) from exc
        return data
