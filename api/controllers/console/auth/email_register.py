import logging
from decimal import Decimal

from flask import make_response, request
from flask_restx import Resource
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import sessionmaker

from configs import dify_config
from constants.languages import languages
from controllers.console import console_ns
from controllers.console.auth.error import (
    EmailAlreadyInUseError,
    EmailCodeError,
    EmailRegisterLimitError,
    InvalidEmailError,
    InvalidTokenError,
    PasswordMismatchError,
)
from extensions.ext_database import db
from libs.helper import EmailStr, extract_remote_ip
from libs.password import valid_password
from libs.token import (
    set_access_token_to_cookie,
    set_csrf_token_to_cookie,
    set_refresh_token_to_cookie,
)
from models import Account
from services.account_service import AccountService
from services.billing_service import BillingService
from services.errors.account import AccountNotFoundError, AccountRegisterError
from services.invitation_service import InvitationService
from services.wallet.tenant_balance_service import TenantBalanceService

from ..error import AccountInFreezeError, EmailSendIpLimitError
from ..wraps import email_password_login_enabled, email_register_enabled, setup_required

logger = logging.getLogger(__name__)

DEFAULT_REF_TEMPLATE_SWAGGER_2_0 = "#/definitions/{model}"


class EmailRegisterSendPayload(BaseModel):
    email: EmailStr = Field(..., description="Email address")
    language: str | None = Field(default=None, description="Language code")


class EmailRegisterValidityPayload(BaseModel):
    email: EmailStr = Field(...)
    code: str = Field(...)
    token: str = Field(...)


class EmailRegisterResetPayload(BaseModel):
    token: str = Field(...)
    new_password: str = Field(...)
    password_confirm: str = Field(...)
    # Optional invite code captured from the signup URL. Bound inside the
    # registration transaction so the referral link survives — a separate
    # POST /creator/invitations/bind call cannot work here: the freshly
    # created account has no auth cookie yet (the frontend only gets the
    # token_pair back in JSON), so @login_required would reject it.
    invite_code: str | None = Field(default=None)

    @field_validator("new_password", "password_confirm")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return valid_password(value)


for model in (EmailRegisterSendPayload, EmailRegisterValidityPayload, EmailRegisterResetPayload):
    console_ns.schema_model(model.__name__, model.model_json_schema(ref_template=DEFAULT_REF_TEMPLATE_SWAGGER_2_0))


@console_ns.route("/email-register/send-email")
class EmailRegisterSendEmailApi(Resource):
    @setup_required
    @email_password_login_enabled
    @email_register_enabled
    def post(self):
        args = EmailRegisterSendPayload.model_validate(console_ns.payload)
        normalized_email = args.email.lower()

        ip_address = extract_remote_ip(request)
        if AccountService.is_email_send_ip_limit(ip_address):
            raise EmailSendIpLimitError()
        language = "en-US"
        if args.language in languages:
            language = args.language

        if dify_config.BILLING_ENABLED and BillingService.is_email_in_freeze(normalized_email):
            raise AccountInFreezeError()

        with sessionmaker(db.engine).begin() as session:
            account = AccountService.get_account_by_email_with_case_fallback(args.email, session=session)
            # Read fields inside the session to avoid DetachedInstanceError after session closes
            account_name = account.name if account else None
        token = AccountService.send_email_register_email(
            email=normalized_email,
            account_name=account_name,
            language=language,
        )
        return {"result": "success", "data": token}


@console_ns.route("/email-register/validity")
class EmailRegisterCheckApi(Resource):
    @setup_required
    @email_password_login_enabled
    @email_register_enabled
    def post(self):
        args = EmailRegisterValidityPayload.model_validate(console_ns.payload)

        user_email = args.email.lower()

        is_email_register_error_rate_limit = AccountService.is_email_register_error_rate_limit(user_email)
        if is_email_register_error_rate_limit:
            raise EmailRegisterLimitError()

        token_data = AccountService.get_email_register_data(args.token)
        if token_data is None:
            raise InvalidTokenError()

        token_email = token_data.get("email")
        normalized_token_email = token_email.lower() if isinstance(token_email, str) else token_email

        if user_email != normalized_token_email:
            raise InvalidEmailError()

        if args.code != token_data.get("code"):
            AccountService.add_email_register_error_rate_limit(user_email)
            raise EmailCodeError()

        # Verified, revoke the first token
        AccountService.revoke_email_register_token(args.token)

        # Refresh token data by generating a new token
        _, new_token = AccountService.generate_email_register_token(
            user_email, code=args.code, additional_data={"phase": "register"}
        )

        AccountService.reset_email_register_error_rate_limit(user_email)
        return {"is_valid": True, "email": normalized_token_email, "token": new_token}


@console_ns.route("/email-register")
class EmailRegisterResetApi(Resource):
    @setup_required
    @email_password_login_enabled
    @email_register_enabled
    def post(self):
        args = EmailRegisterResetPayload.model_validate(console_ns.payload)

        # Validate passwords match
        if args.new_password != args.password_confirm:
            raise PasswordMismatchError()

        # Validate token and get register data
        register_data = AccountService.get_email_register_data(args.token)
        if not register_data:
            raise InvalidTokenError()
        # Must use token in reset phase
        if register_data.get("phase", "") != "register":
            raise InvalidTokenError()

        # Revoke token to prevent reuse
        AccountService.revoke_email_register_token(args.token)

        email = register_data.get("email", "")
        normalized_email = email.lower()

        with sessionmaker(db.engine).begin() as session:
            account = AccountService.get_account_by_email_with_case_fallback(email, session=session)

            if account:
                raise EmailAlreadyInUseError()
            else:
                account = self._create_new_account(normalized_email, args.password_confirm)
                if not account:
                    raise AccountNotFoundError()
                token_pair = AccountService.login(account=account, ip_address=extract_remote_ip(request))
                AccountService.reset_login_error_rate_limit(normalized_email)

        # Best-effort invite-code binding.
        # Ordering: must run AFTER account creation (needs account.id) and
        # AFTER the account/tenant transaction closes, because
        # create_account_and_tenant commits on db.session. Binding failures
        # (bad code, already used, self-invite) must NOT roll back the
        # successful registration — the user is already logged in and we
        # fall through to returning the token_pair. The operator-visible
        # reason lands in logs so a support engineer can re-attempt the
        # bind via POST /creator/invitations/bind if needed.
        if args.invite_code:
            try:
                result = InvitationService.bind_invite_code(
                    invite_code=args.invite_code,
                    invitee_account_id=account.id,
                )
                if result.ok:
                    db.session.commit()
                    logger.info(
                        "Invite bound during registration account=%s inviter=%s",
                        account.id,
                        result.inviter_account_id,
                    )
                else:
                    db.session.rollback()
                    logger.warning(
                        "Invite bind skipped during registration account=%s outcome=%s",
                        account.id,
                        result.outcome.value,
                    )
            except Exception:
                db.session.rollback()
                logger.exception(
                    "Invite bind errored during registration account=%s", account.id
                )

        # Grant signup bonus (¥50) to the new user's workspace.
        try:
            tenant_id = str(account.current_tenant_id)
            SIGNUP_BONUS = Decimal(50)
            TenantBalanceService.topup(tenant_id=tenant_id, amount=SIGNUP_BONUS)
            db.session.commit()
            logger.info("Signup bonus ¥%s granted to tenant=%s account=%s", SIGNUP_BONUS, tenant_id, account.id)
        except Exception:
            db.session.rollback()
            logger.exception("Failed to grant signup bonus for account=%s", account.id)

        # Set auth cookies so the browser is logged in immediately —
        # no separate login step required after registration.
        response = make_response({"result": "success"})
        set_access_token_to_cookie(request, response, token_pair.access_token)
        set_refresh_token_to_cookie(request, response, token_pair.refresh_token)
        set_csrf_token_to_cookie(request, response, token_pair.csrf_token)
        return response

    def _create_new_account(self, email: str, password: str) -> Account | None:
        # Create new account if allowed
        account = None
        try:
            account = AccountService.create_account_and_tenant(
                email=email,
                name=email,
                password=password,
                interface_language=languages[0],
            )
        except AccountRegisterError:
            raise AccountInFreezeError()

        return account
