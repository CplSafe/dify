"""Phone + SMS verification code login/register endpoint."""

import logging
from decimal import Decimal

from flask import make_response, request
from flask_restx import Resource
from pydantic import BaseModel, Field

from constants.languages import languages
from controllers.console import console_ns
from controllers.console.error import AccountBannedError, NotAllowedCreateWorkspace, WorkspacesLimitExceeded
from controllers.console.wraps import setup_required, sms_login_enabled
from events.tenant_event import tenant_was_created
from extensions.ext_database import db
from libs.helper import extract_remote_ip
from libs.token import (
    set_access_token_to_cookie,
    set_csrf_token_to_cookie,
    set_refresh_token_to_cookie,
)
from models.account import Account, AccountStatus
from services.account_service import AccountService, RegisterService, TenantService
from services.errors.workspace import WorkSpaceNotAllowedCreateError, WorkspacesLimitExceededError
from services.feature_service import FeatureService
from services.sms_service import SmsService
from services.wallet.tenant_balance_service import TenantBalanceService

logger = logging.getLogger(__name__)

DEFAULT_REF_TEMPLATE_SWAGGER_2_0 = "#/definitions/{model}"


class SmsSendPayload(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, description="手机号码")


class SmsVerifyPayload(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11, description="手机号码")
    code: str = Field(..., min_length=4, max_length=8, description="短信验证码")
    invite_token: str | None = Field(default=None, description="成员邀请 token")


for model in (SmsSendPayload, SmsVerifyPayload):
    console_ns.schema_model(model.__name__, model.model_json_schema(ref_template=DEFAULT_REF_TEMPLATE_SWAGGER_2_0))


@console_ns.route("/sms-login/send-code")
class SmsLoginSendCodeApi(Resource):
    """Send SMS verification code to a phone number."""

    @setup_required
    @sms_login_enabled
    def post(self):
        args = SmsSendPayload.model_validate(console_ns.payload)
        phone = args.phone.strip()

        try:
            SmsService.send_verification_code(phone)
        except ValueError as e:
            return {"code": "sms_rate_limit", "message": str(e), "status": 429}, 429

        return {"result": "success"}


@console_ns.route("/sms-login/verify")
class SmsLoginVerifyApi(Resource):
    """Verify SMS code, auto-register if needed, then login."""

    @setup_required
    @sms_login_enabled
    def post(self):
        args = SmsVerifyPayload.model_validate(console_ns.payload)
        phone = args.phone.strip()

        # Verify SMS code
        if not SmsService.verify_code(phone, args.code):
            return {"code": "sms_code_error", "message": "验证码无效或已过期", "status": 400}, 400

        # Resolve invite_token if present
        invitation_data = None
        if args.invite_token:
            if RegisterService.is_valid_invite_token(args.invite_token):
                invitation_data = RegisterService.get_invitation_by_token(token=args.invite_token)
            if not invitation_data:
                return {"code": "invalid_invite", "message": "邀请链接无效或已过期", "status": 400}, 400

        # ── Invite flow: find the invited account by email, bind phone ──
        if invitation_data:
            invited_email = invitation_data.get("email", "")
            account = db.session.query(Account).filter(Account.email == invited_email).first()
            if not account:
                return {"code": "account_not_found", "message": "邀请的账号不存在", "status": 400}, 400

            if account.status == AccountStatus.BANNED:
                raise AccountBannedError()

            # Check if this phone is already used by a different account
            existing_phone_account = db.session.query(Account).filter(Account.phone == phone).first()
            if existing_phone_account and existing_phone_account.id != account.id:
                return {
                    "code": "phone_already_bound",
                    "message": "该手机号已被其他账号绑定",
                    "status": 409,
                }, 409

            # Bind phone and activate
            account.phone = phone
            if account.status == AccountStatus.PENDING:
                account.status = AccountStatus.ACTIVE
            db.session.commit()

            # Switch to the invited workspace
            workspace_id = invitation_data.get("workspace_id")
            if workspace_id:
                TenantService.switch_tenant(account, workspace_id)

            # Revoke invite token
            RegisterService.revoke_token(
                workspace_id=workspace_id,
                email=account.email,
                token=args.invite_token,
            )

            token_pair = AccountService.login(account, ip_address=extract_remote_ip(request))
            AccountService.reset_login_error_rate_limit(phone)

            response = make_response({"result": "success"})
            set_access_token_to_cookie(request, response, token_pair.access_token)
            set_refresh_token_to_cookie(request, response, token_pair.refresh_token)
            set_csrf_token_to_cookie(request, response, token_pair.csrf_token)
            return response

        # ── Normal flow: find or create account by phone ──
        account = db.session.query(Account).filter(Account.phone == phone).first()
        is_new_account = False

        if account is None:
            account = self._create_account_by_phone(phone)
            is_new_account = True
        else:
            if account.status == AccountStatus.BANNED:
                raise AccountBannedError()

            # Ensure tenant exists
            tenants = TenantService.get_join_tenants(account)
            if not tenants:
                workspaces = FeatureService.get_system_features().license.workspaces
                if not workspaces.is_available():
                    raise WorkspacesLimitExceeded()
                if not FeatureService.get_system_features().is_allow_create_workspace:
                    raise NotAllowedCreateWorkspace()
                new_tenant = TenantService.create_tenant(f"{account.name}'s Workspace")
                TenantService.create_tenant_member(new_tenant, account, role="owner")
                account.current_tenant = new_tenant
                tenant_was_created.send(new_tenant)

        token_pair = AccountService.login(account, ip_address=extract_remote_ip(request))
        AccountService.reset_login_error_rate_limit(phone)

        # Grant signup bonus for new accounts
        if is_new_account:
            self._grant_signup_bonus(account)

        response = make_response({"result": "success"})
        set_access_token_to_cookie(request, response, token_pair.access_token)
        set_refresh_token_to_cookie(request, response, token_pair.refresh_token)
        set_csrf_token_to_cookie(request, response, token_pair.csrf_token)
        return response

    def _create_account_by_phone(self, phone: str) -> Account:
        """Create a new account + tenant for phone-based registration."""
        placeholder_email = f"{phone}@sms.local"

        try:
            account = AccountService.create_account_and_tenant(
                email=placeholder_email,
                name=phone,
                interface_language=languages[0],
            )
        except WorkSpaceNotAllowedCreateError:
            raise NotAllowedCreateWorkspace()
        except WorkspacesLimitExceededError:
            raise WorkspacesLimitExceeded()

        account.phone = phone
        db.session.commit()
        return account

    def _grant_signup_bonus(self, account: Account) -> None:
        try:
            tenant_id = str(account.current_tenant_id)
            SIGNUP_BONUS = Decimal(50)
            TenantBalanceService.topup(tenant_id=tenant_id, amount=SIGNUP_BONUS)
            db.session.commit()
            logger.info("Signup bonus ¥%s granted to tenant=%s account=%s", SIGNUP_BONUS, tenant_id, account.id)
        except Exception:
            db.session.rollback()
            logger.exception("Failed to grant signup bonus for account=%s", account.id)
