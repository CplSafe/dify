from flask import make_response, request
from flask_restx import Resource
from jwt import InvalidTokenError
from pydantic import BaseModel, Field, field_validator

import services
from configs import dify_config
from controllers.common.schema import register_schema_models
from controllers.console.auth.error import (
    AuthenticationFailedError,
    EmailCodeError,
    InvalidEmailError,
)
from controllers.console.error import AccountBannedError
from controllers.console.wraps import (
    decrypt_code_field,
    decrypt_password_field,
    only_edition_enterprise,
    setup_required,
)
from controllers.web import web_ns
from controllers.web.wraps import decode_jwt_token
from libs.helper import EmailStr
from libs.passport import PassportService
from libs.password import valid_password
from libs.token import (
    clear_webapp_access_token_from_cookie,
    extract_webapp_access_token,
)
from services.account_service import AccountService
from services.app_service import AppService
from services.webapp_auth_service import WebAppAuthService


class LoginPayload(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return valid_password(value)


class EmailCodeLoginSendPayload(BaseModel):
    email: EmailStr
    language: str | None = None


class EmailCodeLoginVerifyPayload(BaseModel):
    email: EmailStr
    code: str
    token: str = Field(min_length=1)


register_schema_models(web_ns, LoginPayload, EmailCodeLoginSendPayload, EmailCodeLoginVerifyPayload)


@web_ns.route("/login")
class LoginApi(Resource):
    """Resource for web app email/password login."""

    @web_ns.expect(web_ns.models[LoginPayload.__name__])
    @setup_required
    @only_edition_enterprise
    @web_ns.doc(
        description="企业版 Web 应用账号密码登录。"
                    "登录成功后返回 access_token，后续请求需在 Authorization 头中携带该令牌。",
        responses={
            200: "登录成功，返回 access_token",
            400: "请求格式错误（邮箱或密码格式不合法）",
            401: "认证失败（邮箱或密码错误）",
            403: "账号已封禁或该版本不支持此登录方式",
            404: "账号不存在",
        },
    )
    @decrypt_password_field
    def post(self):
        """企业版 Web 应用账号密码登录"""
        payload = LoginPayload.model_validate(web_ns.payload or {})

        try:
            account = WebAppAuthService.authenticate(payload.email, payload.password)
        except services.errors.account.AccountLoginError:
            raise AccountBannedError()
        except services.errors.account.AccountPasswordError:
            raise AuthenticationFailedError()
        except services.errors.account.AccountNotFoundError:
            raise AuthenticationFailedError()

        token = WebAppAuthService.login(account=account)
        response = make_response({"result": "success", "data": {"access_token": token}})
        # set_access_token_to_cookie(request, response, token, samesite="None", httponly=False)
        return response


# this api helps frontend to check whether user is authenticated
# TODO: remove in the future. frontend should redirect to login page by catching 401 status
@web_ns.route("/login/status")
class LoginStatusApi(Resource):
    @setup_required
    @web_ns.doc(
        description="检查当前用户及应用的登录状态。"
                    "前端可通过此接口判断是否需要跳转到登录页，"
                    "返回 logged_in（用户级别）和 app_logged_in（应用级别）两个状态位。",
        params={
            "app_code": "可选，Web 应用 code，用于检查应用级别登录状态",
            "user_id": "可选，用户 ID",
        },
        responses={
            200: "成功，返回登录状态",
        },
    )
    def get(self):
        """检查用户及应用登录状态"""
        app_code = request.args.get("app_code")
        user_id = request.args.get("user_id")
        token = extract_webapp_access_token(request)
        if not app_code:
            return {
                "logged_in": bool(token),
                "app_logged_in": False,
            }
        app_id = AppService.get_app_id_by_code(app_code)
        is_public = not dify_config.ENTERPRISE_ENABLED or not WebAppAuthService.is_app_require_permission_check(
            app_id=app_id
        )
        user_logged_in = False

        if is_public:
            user_logged_in = True
        else:
            try:
                PassportService().verify(token=token)
                user_logged_in = True
            except Exception:
                user_logged_in = False

        try:
            _ = decode_jwt_token(app_code=app_code, user_id=user_id)
            app_logged_in = True
        except Exception:
            app_logged_in = False

        return {
            "logged_in": user_logged_in,
            "app_logged_in": app_logged_in,
        }


@web_ns.route("/logout")
class LogoutApi(Resource):
    @setup_required
    @web_ns.doc(
        description="退出登录，清除 Cookie 中的 access_token。"
                    "企业 SSO 场景下 Cookie SameSite=None，需通过此接口主动清除。",
        responses={
            200: "退出成功",
        },
    )
    def post(self):
        """退出 Web 应用登录"""
        response = make_response({"result": "success"})
        # enterprise SSO sets same site to None in https deployment
        # so we need to logout by calling api
        clear_webapp_access_token_from_cookie(response, samesite="None")
        return response


@web_ns.route("/email-code-login")
class EmailCodeLoginSendEmailApi(Resource):
    @setup_required
    @only_edition_enterprise
    @web_ns.expect(web_ns.models[EmailCodeLoginSendPayload.__name__])
    @web_ns.doc(
        description="发送邮箱验证码登录邮件（企业版）。"
                    "调用后系统向指定邮箱发送验证码，用户需在 /email-code-login/validity 接口提交验证码完成登录。",
        responses={
            200: "邮件发送成功，返回 token",
            400: "请求格式错误（邮箱格式不合法）",
            401: "认证失败（邮箱不存在）",
        },
    )
    def post(self):
        """发送邮箱验证码登录邮件"""
        payload = EmailCodeLoginSendPayload.model_validate(web_ns.payload or {})

        if payload.language == "zh-Hans":
            language = "zh-Hans"
        else:
            language = "en-US"

        account = WebAppAuthService.get_user_through_email(payload.email)
        if account is None:
            raise AuthenticationFailedError()
        else:
            token = WebAppAuthService.send_email_code_login_email(account=account, language=language)
        return {"result": "success", "data": token}


@web_ns.route("/email-code-login/validity")
class EmailCodeLoginApi(Resource):
    @setup_required
    @only_edition_enterprise
    @web_ns.expect(web_ns.models[EmailCodeLoginVerifyPayload.__name__])
    @web_ns.doc(
        description="验证邮箱验证码并完成登录（企业版）。"
                    "需传入 /email-code-login 返回的 token、邮箱和用户收到的验证码。"
                    "验证通过后返回 access_token。",
        responses={
            200: "验证成功，返回 access_token",
            400: "请求格式错误",
            401: "token 无效或验证码错误",
            404: "账号不存在",
        },
    )
    @decrypt_code_field
    def post(self):
        """验证邮箱验证码并完成登录"""
        payload = EmailCodeLoginVerifyPayload.model_validate(web_ns.payload or {})

        user_email = payload.email.lower()

        token_data = WebAppAuthService.get_email_code_login_data(payload.token)
        if token_data is None:
            raise InvalidTokenError()

        token_email = token_data.get("email")
        if not isinstance(token_email, str):
            raise InvalidEmailError()
        normalized_token_email = token_email.lower()
        if normalized_token_email != user_email:
            raise InvalidEmailError()

        if token_data["code"] != payload.code:
            raise EmailCodeError()

        WebAppAuthService.revoke_email_code_login_token(payload.token)
        account = WebAppAuthService.get_user_through_email(token_email)
        if not account:
            raise AuthenticationFailedError()

        token = WebAppAuthService.login(account=account)
        AccountService.reset_login_error_rate_limit(user_email)
        response = make_response({"result": "success", "data": {"access_token": token}})
        # set_access_token_to_cookie(request, response, token, samesite="None", httponly=False)
        return response
