import inspect
import logging
import time
from collections.abc import Callable
from enum import StrEnum, auto
from functools import wraps
from typing import cast, overload

from flask import current_app, request
from flask_login import user_logged_in
from flask_restx import Resource
from pydantic import BaseModel
from sqlalchemy import select
from werkzeug.exceptions import Forbidden, NotFound, Unauthorized

from enums.cloud_plan import CloudPlan
from extensions.ext_database import db
from extensions.ext_redis import redis_client
from libs.login import current_user
from models import Account, Tenant, TenantAccountJoin, TenantStatus
from models.dataset import Dataset, RateLimitLog
from models.model import ApiToken, App
from services.api_token_service import ApiTokenCache, fetch_token_with_single_flight, record_token_usage
from services.end_user_service import EndUserService
from services.feature_service import FeatureService

logger = logging.getLogger(__name__)


class WhereisUserArg(StrEnum):
    """
    Enum for whereis_user_arg.
    """

    QUERY = auto()
    JSON = auto()
    FORM = auto()


class FetchUserArg(BaseModel):
    fetch_from: WhereisUserArg
    required: bool = False


@overload
def validate_app_token[**P, R](view: Callable[P, R]) -> Callable[P, R]: ...


@overload
def validate_app_token[**P, R](
    view: None = None, *, fetch_user_arg: FetchUserArg | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def validate_app_token[**P, R](
    view: Callable[P, R] | None = None, *, fetch_user_arg: FetchUserArg | None = None
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(view_func: Callable[P, R]) -> Callable[P, R]:
        @wraps(view_func)
        def decorated_view(*args: P.args, **kwargs: P.kwargs) -> R:
            api_token = validate_and_get_api_token("app")

            app_model = db.session.get(App, api_token.app_id)
            if not app_model:
                raise Forbidden("The app no longer exists.")

            if app_model.status != "normal":
                raise Forbidden("The app's status is abnormal.")

            if not app_model.enable_api:
                raise Forbidden("The app's API service has been disabled.")

            tenant = db.session.get(Tenant, app_model.tenant_id)
            if tenant is None:
                raise ValueError("Tenant does not exist.")
            if tenant.status == TenantStatus.ARCHIVE:
                raise Forbidden("The workspace's status is archived.")

            kwargs["app_model"] = app_model

            # If caller needs end-user context, attach EndUser to current_user
            if fetch_user_arg:
                user_id = None
                match fetch_user_arg.fetch_from:
                    case WhereisUserArg.QUERY:
                        user_id = request.args.get("user")
                    case WhereisUserArg.JSON:
                        user_id = request.get_json().get("user")
                    case WhereisUserArg.FORM:
                        user_id = request.form.get("user")

                if not user_id and fetch_user_arg.required:
                    raise ValueError("Arg user must be provided.")

                if user_id:
                    user_id = str(user_id)

                end_user = EndUserService.get_or_create_end_user(app_model, user_id)
                kwargs["end_user"] = end_user

                # Set EndUser as current logged-in user for flask_login.current_user
                current_app.login_manager._update_request_context_with_user(end_user)  # type: ignore
                user_logged_in.send(current_app._get_current_object(), user=end_user)  # type: ignore
            else:
                # For service API without end-user context, ensure an Account is logged in
                # so services relying on current_account_with_tenant() work correctly.
                tenant_owner_info = db.session.execute(
                    select(Tenant, Account)
                    .join(TenantAccountJoin, Tenant.id == TenantAccountJoin.tenant_id)
                    .join(Account, TenantAccountJoin.account_id == Account.id)
                    .where(
                        Tenant.id == app_model.tenant_id,
                        TenantAccountJoin.role == "owner",
                        Tenant.status == TenantStatus.NORMAL,
                    )
                ).one_or_none()

                if tenant_owner_info:
                    tenant_model, account = tenant_owner_info
                    account.current_tenant = tenant_model
                    current_app.login_manager._update_request_context_with_user(account)  # type: ignore
                    user_logged_in.send(current_app._get_current_object(), user=current_user)  # type: ignore
                else:
                    raise Unauthorized("Tenant owner account not found or tenant is not active.")

            return view_func(*args, **kwargs)

        return decorated_view

    if view is None:
        return decorator
    else:
        return decorator(view)


def cloud_edition_billing_resource_check[**P, R](
    resource: str,
    api_token_type: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def interceptor(view: Callable[P, R]):
        def decorated(*args: P.args, **kwargs: P.kwargs):
            api_token = validate_and_get_api_token(api_token_type)
            features = FeatureService.get_features(api_token.tenant_id)

            if features.billing.enabled:
                members = features.members
                apps = features.apps
                vector_space = features.vector_space
                documents_upload_quota = features.documents_upload_quota

                if resource == "members" and 0 < members.limit <= members.size:
                    raise Forbidden("The number of members has reached the limit of your subscription.")
                elif resource == "apps" and 0 < apps.limit <= apps.size:
                    raise Forbidden("The number of apps has reached the limit of your subscription.")
                elif resource == "vector_space" and 0 < vector_space.limit <= vector_space.size:
                    raise Forbidden("The capacity of the vector space has reached the limit of your subscription.")
                elif resource == "documents" and 0 < documents_upload_quota.limit <= documents_upload_quota.size:
                    raise Forbidden("The number of documents has reached the limit of your subscription.")
                else:
                    return view(*args, **kwargs)

            return view(*args, **kwargs)

        return decorated

    return interceptor


def cloud_edition_billing_knowledge_limit_check[**P, R](
    resource: str,
    api_token_type: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def interceptor(view: Callable[P, R]):
        @wraps(view)
        def decorated(*args: P.args, **kwargs: P.kwargs):
            api_token = validate_and_get_api_token(api_token_type)
            features = FeatureService.get_features(api_token.tenant_id)
            if features.billing.enabled:
                if resource == "add_segment":
                    if features.billing.subscription.plan == CloudPlan.SANDBOX:
                        raise Forbidden(
                            "To unlock this feature and elevate your Dify experience, please upgrade to a paid plan."
                        )
                else:
                    return view(*args, **kwargs)

            return view(*args, **kwargs)

        return decorated

    return interceptor


def cloud_edition_billing_rate_limit_check[**P, R](
    resource: str,
    api_token_type: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def interceptor(view: Callable[P, R]):
        @wraps(view)
        def decorated(*args: P.args, **kwargs: P.kwargs):
            api_token = validate_and_get_api_token(api_token_type)

            if resource == "knowledge":
                knowledge_rate_limit = FeatureService.get_knowledge_rate_limit(api_token.tenant_id)
                if knowledge_rate_limit.enabled:
                    current_time = int(time.time() * 1000)
                    key = f"rate_limit_{api_token.tenant_id}"

                    redis_client.zadd(key, {current_time: current_time})

                    redis_client.zremrangebyscore(key, 0, current_time - 60000)

                    request_count = redis_client.zcard(key)

                    if request_count > knowledge_rate_limit.limit:
                        # add ratelimit record
                        rate_limit_log = RateLimitLog(
                            tenant_id=api_token.tenant_id,
                            subscription_plan=knowledge_rate_limit.subscription_plan,
                            operation="knowledge",
                        )
                        db.session.add(rate_limit_log)
                        db.session.commit()
                        raise Forbidden(
                            "Sorry, you have reached the knowledge base request rate limit of your subscription."
                        )
            return view(*args, **kwargs)

        return decorated

    return interceptor


def validate_dataset_token[R](view: Callable[..., R]) -> Callable[..., R]:
    positional_parameters = [
        parameter
        for parameter in inspect.signature(view).parameters.values()
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    expects_bound_instance = bool(positional_parameters and positional_parameters[0].name in {"self", "cls"})

    @wraps(view)
    def decorated(*args: object, **kwargs: object) -> R:
        api_token = validate_and_get_api_token("dataset")

        # Flask may pass URL path parameters positionally, so inspect both kwargs and args.
        dataset_id = kwargs.get("dataset_id")

        if not dataset_id and args:
            potential_id = args[0]
            try:
                str_id = str(potential_id)
                if len(str_id) == 36 and str_id.count("-") == 4:
                    dataset_id = str_id
            except Exception:
                logger.exception("Failed to parse dataset_id from positional args")

        if dataset_id:
            dataset_id = str(dataset_id)
            dataset = db.session.scalar(
                select(Dataset)
                .where(
                    Dataset.id == dataset_id,
                    Dataset.tenant_id == api_token.tenant_id,
                )
                .limit(1)
            )
            if not dataset:
                raise NotFound("Dataset not found.")
            if not dataset.enable_api:
                raise Forbidden("Dataset api access is not enabled.")

        tenant_account_join = db.session.execute(
            select(Tenant, TenantAccountJoin)
            .where(Tenant.id == api_token.tenant_id)
            .where(TenantAccountJoin.tenant_id == Tenant.id)
            .where(TenantAccountJoin.role.in_(["owner"]))
            .where(Tenant.status == TenantStatus.NORMAL)
        ).one_or_none()  # TODO: only owner information is required, so only one is returned.
        if tenant_account_join:
            tenant, ta = tenant_account_join
            account = db.session.get(Account, ta.account_id)
            # Login admin
            if account:
                account.current_tenant = tenant
                current_app.login_manager._update_request_context_with_user(account)  # type: ignore
                user_logged_in.send(current_app._get_current_object(), user=current_user)  # type: ignore
            else:
                raise Unauthorized("Tenant owner account does not exist.")
        else:
            raise Unauthorized("Tenant does not exist.")

        if expects_bound_instance:
            if not args:
                raise TypeError("validate_dataset_token expected a bound resource instance.")
            return view(args[0], api_token.tenant_id, *args[1:], **kwargs)

        return view(api_token.tenant_id, *args, **kwargs)

    return decorated


def _resolve_ugak_token(auth_token: str, scope: str | None) -> "ApiToken":
    """Validate a ugak- prefixed user global API key and return a token-like object.

    Looks up the UserGlobalApiKey, finds the target app (from request body or first
    active MarketplaceApp), and returns a CachedApiToken with the app/tenant info.
    """
    from models.creator import MarketplaceApp, UserGlobalApiKey
    from services.api_token_service import CachedApiToken

    ugak = db.session.scalar(
        select(UserGlobalApiKey).where(UserGlobalApiKey.token == auth_token)
    )
    if ugak is None:
        raise Unauthorized("Invalid API key.")

    # Determine which app to use: prefer explicit app_id from request, else first active app
    request_json = request.get_json(silent=True, force=True) or {}
    app_id = request.args.get("app_id") or request_json.get("app_id")

    if app_id:
        marketplace_entry = db.session.scalar(
            select(MarketplaceApp).where(
                MarketplaceApp.app_id == str(app_id),
                MarketplaceApp.is_active == True,
            )
        )
        if not marketplace_entry:
            raise Unauthorized("App is not available in the creator marketplace.")
    else:
        marketplace_entry = db.session.scalar(
            select(MarketplaceApp)
            .where(MarketplaceApp.is_active == True)
            .order_by(MarketplaceApp.display_order.asc())
            .limit(1)
        )
        if not marketplace_entry:
            raise Unauthorized("No active marketplace apps available.")
        app_id = marketplace_entry.app_id

    app_model = db.session.get(App, str(app_id))
    if not app_model:
        raise Unauthorized("The app no longer exists.")

    # Try to find an existing ApiToken for this app; if none exists, create a synthetic one
    existing_token = db.session.scalar(
        select(ApiToken).where(
            ApiToken.app_id == str(app_id),
            ApiToken.type == "app",
        ).limit(1)
    )

    if existing_token:
        return cast(ApiToken, CachedApiToken(
            id=str(existing_token.id),
            app_id=str(existing_token.app_id) if existing_token.app_id else None,
            tenant_id=str(existing_token.tenant_id) if existing_token.tenant_id else None,
            type=str(existing_token.type),
            token=existing_token.token,
            last_used_at=existing_token.last_used_at,
            created_at=existing_token.created_at,
        ))

    # No real ApiToken exists — build a synthetic one from the app model
    return cast(ApiToken, CachedApiToken(
        id=ugak.id,
        app_id=str(app_id),
        tenant_id=str(app_model.tenant_id),
        type="app",
        token=auth_token,
        last_used_at=ugak.last_used_at,
        created_at=ugak.created_at,
    ))


def validate_and_get_api_token(scope: str | None = None):
    """
    Validate and get API token with Redis caching.

    This function uses a two-tier approach:
    1. First checks Redis cache for the token
    2. If not cached, queries database and caches the result

    The last_used_at field is updated asynchronously via Celery task
    to avoid blocking the request.

    ugak- prefixed tokens (User Global API Keys) are handled separately:
    they bypass the normal cache flow and resolve via the UserGlobalApiKey table.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header is None or " " not in auth_header:
        raise Unauthorized("Authorization header must be provided and start with 'Bearer'")

    auth_scheme, auth_token = auth_header.split(None, 1)
    auth_scheme = auth_scheme.lower()

    if auth_scheme != "bearer":
        raise Unauthorized("Authorization scheme must be 'Bearer'")

    # Handle user global API keys (ugak- prefix) directly without cache
    if auth_token.startswith("ugak-"):
        return _resolve_ugak_token(auth_token, scope)

    # Try to get token from cache first
    # Returns a CachedApiToken (plain Python object), not a SQLAlchemy model
    cached_token = ApiTokenCache.get(auth_token, scope)
    if cached_token is not None:
        logger.debug("Token validation served from cache for scope: %s", scope)
        # Record usage in Redis for later batch update (no Celery task per request)
        record_token_usage(auth_token, scope)
        return cast(ApiToken, cached_token)

    # Cache miss - use Redis lock for single-flight mode
    # This ensures only one request queries DB for the same token concurrently
    return fetch_token_with_single_flight(auth_token, scope)


class DatasetApiResource(Resource):
    method_decorators = [validate_dataset_token]

    def get_dataset(self, dataset_id: str, tenant_id: str) -> Dataset:
        dataset = db.session.scalar(
            select(Dataset).where(Dataset.id == dataset_id, Dataset.tenant_id == tenant_id).limit(1)
        )

        if not dataset:
            raise NotFound("Dataset not found.")

        return dataset
