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
    def get(self):
        """List current tenant's bound social accounts."""
        _, current_tenant_id = current_account_with_tenant()
        platform = request.args.get("platform") or None
        try:
            service = _build_service()
            accounts = service.list_accounts(tenant_id=current_tenant_id, platform=platform)
        except Exception as exc:
            raise _to_http_error(exc) from exc

        return {"data": [a.to_dict() for a in accounts]}


@console_ns.route("/social-publish/accounts/auth/start")
class SocialPublishAuthStartApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def post(self):
        """Begin an auth session and return a QR image."""
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
    def get(self, session_id: str):
        """Poll the status of a sau auth session."""
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
        }


@console_ns.route("/social-publish/accounts/<string:account_id>")
class SocialPublishAccountItemApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, account_id: str):
        """Delete an account; tells sau to drop the cookie best-effort."""
        _, current_tenant_id = current_account_with_tenant()
        try:
            service = _build_service()
            service.delete_account(account_id=account_id, tenant_id=current_tenant_id)
        except Exception as exc:
            raise _to_http_error(exc) from exc

        return {"result": "success"}
