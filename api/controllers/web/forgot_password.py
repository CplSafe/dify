import base64
import secrets

from flask import request
from flask_restx import Resource
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import sessionmaker

from controllers.common.schema import register_schema_models
from controllers.console.auth.error import (
    AuthenticationFailedError,
    EmailCodeError,
    EmailPasswordResetLimitError,
    InvalidEmailError,
    InvalidTokenError,
    PasswordMismatchError,
)
from controllers.console.error import EmailSendIpLimitError
from controllers.console.wraps import email_password_login_enabled, only_edition_enterprise, setup_required
from controllers.web import web_ns
from extensions.ext_database import db
from libs.helper import EmailStr, extract_remote_ip
from libs.password import hash_password, valid_password
from models.account import Account
from services.account_service import AccountService


class ForgotPasswordSendPayload(BaseModel):
    email: EmailStr
    language: str | None = None


class ForgotPasswordCheckPayload(BaseModel):
    email: EmailStr
    code: str
    token: str = Field(min_length=1)


class ForgotPasswordResetPayload(BaseModel):
    token: str = Field(min_length=1)
    new_password: str
    password_confirm: str

    @field_validator("new_password", "password_confirm")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return valid_password(value)


register_schema_models(web_ns, ForgotPasswordSendPayload, ForgotPasswordCheckPayload, ForgotPasswordResetPayload)


@web_ns.route("/forgot-password")
class ForgotPasswordSendEmailApi(Resource):
    @web_ns.expect(web_ns.models[ForgotPasswordSendPayload.__name__])
    @only_edition_enterprise
    @setup_required
    @email_password_login_enabled
    @web_ns.doc(
        description="发送密码重置邮件（企业版）。"
                    "系统向指定邮箱发送包含验证码的重置邮件，"
                    "随后需在 /forgot-password/validity 接口验证验证码。",
        responses={
            200: "邮件发送成功，返回 token",
            400: "请求格式错误（邮箱格式不合法）",
            401: "认证失败（邮箱不存在）",
            429: "请求频率超限（同 IP 发送次数过多）",
        },
    )
    def post(self):
        """发送密码重置邮件"""
        payload = ForgotPasswordSendPayload.model_validate(web_ns.payload or {})

        request_email = payload.email
        normalized_email = request_email.lower()

        ip_address = extract_remote_ip(request)
        if AccountService.is_email_send_ip_limit(ip_address):
            raise EmailSendIpLimitError()

        if payload.language == "zh-Hans":
            language = "zh-Hans"
        else:
            language = "en-US"

        with sessionmaker(db.engine).begin() as session:
            account = AccountService.get_account_by_email_with_case_fallback(request_email, session=session)
        token = None
        if account is None:
            raise AuthenticationFailedError()
        else:
            token = AccountService.send_reset_password_email(account=account, email=normalized_email, language=language)

        return {"result": "success", "data": token}


@web_ns.route("/forgot-password/validity")
class ForgotPasswordCheckApi(Resource):
    @web_ns.expect(web_ns.models[ForgotPasswordCheckPayload.__name__])
    @only_edition_enterprise
    @setup_required
    @email_password_login_enabled
    @web_ns.doc(
        description="验证密码重置验证码有效性（企业版）。"
                    "验证通过后返回新 token，需在 /forgot-password/resets 接口用此 token 完成密码重置。",
        responses={
            200: "验证成功，返回新 token",
            400: "请求格式错误",
            401: "验证码无效、过期，或超出错误次数限制",
        },
    )
    def post(self):
        """验证密码重置验证码"""
        payload = ForgotPasswordCheckPayload.model_validate(web_ns.payload or {})

        user_email = payload.email.lower()

        is_forgot_password_error_rate_limit = AccountService.is_forgot_password_error_rate_limit(user_email)
        if is_forgot_password_error_rate_limit:
            raise EmailPasswordResetLimitError()

        token_data = AccountService.get_reset_password_data(payload.token)
        if token_data is None:
            raise InvalidTokenError()

        token_email = token_data.get("email")
        if not isinstance(token_email, str):
            raise InvalidEmailError()
        normalized_token_email = token_email.lower()

        if user_email != normalized_token_email:
            raise InvalidEmailError()

        if payload.code != token_data.get("code"):
            AccountService.add_forgot_password_error_rate_limit(user_email)
            raise EmailCodeError()

        # Verified, revoke the first token
        AccountService.revoke_reset_password_token(payload.token)

        # Refresh token data by generating a new token
        _, new_token = AccountService.generate_reset_password_token(
            token_email, code=payload.code, additional_data={"phase": "reset"}
        )

        AccountService.reset_forgot_password_error_rate_limit(user_email)
        return {"is_valid": True, "email": normalized_token_email, "token": new_token}


@web_ns.route("/forgot-password/resets")
class ForgotPasswordResetApi(Resource):
    @web_ns.expect(web_ns.models[ForgotPasswordResetPayload.__name__])
    @only_edition_enterprise
    @setup_required
    @email_password_login_enabled
    @web_ns.doc(
        description="重置用户密码（企业版）。"
                    "需传入 /forgot-password/validity 返回的 token、新密码及确认密码。"
                    "成功后原 token 自动失效，防止重放攻击。",
        responses={
            200: "密码重置成功",
            400: "请求格式错误（两次密码不一致或密码强度不足）",
            401: "token 无效或已过期",
            404: "账号不存在",
        },
    )
    def post(self):
        """重置用户密码"""
        payload = ForgotPasswordResetPayload.model_validate(web_ns.payload or {})

        # Validate passwords match
        if payload.new_password != payload.password_confirm:
            raise PasswordMismatchError()

        # Validate token and get reset data
        reset_data = AccountService.get_reset_password_data(payload.token)
        if not reset_data:
            raise InvalidTokenError()
        # Must use token in reset phase
        if reset_data.get("phase", "") != "reset":
            raise InvalidTokenError()

        # Revoke token to prevent reuse
        AccountService.revoke_reset_password_token(payload.token)

        # Generate secure salt and hash password
        salt = secrets.token_bytes(16)
        password_hashed = hash_password(payload.new_password, salt)

        email = reset_data.get("email", "")

        with sessionmaker(db.engine).begin() as session:
            account = AccountService.get_account_by_email_with_case_fallback(email, session=session)

            if account:
                self._update_existing_account(account, password_hashed, salt)
            else:
                raise AuthenticationFailedError()

        return {"result": "success"}

    def _update_existing_account(self, account: Account, password_hashed, salt):
        # Update existing account credentials
        account.password = base64.b64encode(password_hashed).decode()
        account.password_salt = base64.b64encode(salt).decode()
