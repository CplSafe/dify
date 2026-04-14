from importlib import import_module

from flask import Blueprint, jsonify, request
from flask_restx import Namespace

from libs.external_api import ExternalApi

bp = Blueprint("console", __name__, url_prefix="/console/api")

api = ExternalApi(
    bp,
    version="1.0",
    title="Console API",
    description="Console management APIs for app configuration, monitoring, and administration",
)

console_ns = Namespace("console", description="Console management API operations", path="/")

# Paths that non-admin (creator) users are allowed to access.
# Everything else requires is_system_admin=True.
_CREATOR_ALLOWED_PREFIXES = (
    "/console/api/datasets",
    "/console/api/workspaces",
    "/console/api/files/upload",
    "/console/api/trial-apps/",
    "/console/api/creator/",
    "/console/api/installed-apps",
    "/console/api/workflow/",
    "/console/api/form/human_input/",
    "/console/api/login",
    "/console/api/logout",
    "/console/api/refresh-token",
    "/console/api/email-register",
    "/console/api/forgot-password",
    "/console/api/system-features",
    "/console/api/features",
    "/console/api/setup",
    "/console/api/version",
    "/console/api/ping",
    "/console/api/activate/check",
    "/console/api/activate",
    "/console/api/account/profile",
    "/console/api/account/avatar",
    "/console/api/account/name",
    "/console/api/account/interface-language",
    "/console/api/workspaces/current",
    "/console/api/datasets/retrieval-setting",
)


@bp.before_request
def _enforce_creator_access_control():
    """Block non-admin users from accessing admin-only APIs."""
    # Skip OPTIONS (CORS preflight)
    if request.method == "OPTIONS":
        return None

    # Skip if no auth token — unauthenticated requests are handled by login_required decorators.
    # Accessing current_user here would trigger request_loader which raises Unauthorized
    # for token-less requests, breaking public endpoints like /login and /system-features.
    from libs.token import extract_access_token
    if not extract_access_token(request):
        return None

    from flask_login import current_user

    user = getattr(current_user, "_get_current_object", lambda: current_user)()
    # Not logged in yet — let auth layer handle it
    if not user or not getattr(user, "is_authenticated", False):
        return None

    # System admins have unrestricted access
    if getattr(user, "is_system_admin", False):
        return None

    # Non-admin users: only allow whitelisted prefixes
    path = request.path
    if any(path.startswith(prefix) for prefix in _CREATOR_ALLOWED_PREFIXES):
        return None

    return (
        jsonify({
            "code": "system_admin_required",
            "message": "This API is restricted to system administrators only.",
            "status": 403,
        }),
        403,
    )


RESOURCE_MODULES = (
    "controllers.console.app.app_import",
    "controllers.console.explore.audio",
    "controllers.console.explore.completion",
    "controllers.console.explore.conversation",
    "controllers.console.explore.message",
    "controllers.console.explore.workflow",
    "controllers.console.files",
    "controllers.console.remote_files",
)

for module_name in RESOURCE_MODULES:
    import_module(module_name)

# Ensure resource modules are imported so route decorators are evaluated.
# Import other controllers
from . import (
    admin,
    apikey,
    extension,
    feature,
    human_input_form,
    init_validate,
    notification,
    ping,
    setup,
    spec,
    version,
)

# Import app controllers
from .app import (
    advanced_prompt_template,
    agent,
    annotation,
    app,
    audio,
    completion,
    conversation,
    conversation_variables,
    generator,
    mcp_server,
    message,
    model_config,
    ops_trace,
    site,
    statistic,
    workflow,
    workflow_app_log,
    workflow_draft_variable,
    workflow_run,
    workflow_statistic,
    workflow_trigger,
)

# Import auth controllers
from .auth import (
    activate,
    data_source_bearer_auth,
    data_source_oauth,
    email_register,
    forgot_password,
    login,
    oauth,
    oauth_server,
)

# Import billing controllers
from .billing import billing, compliance

# Import creator controllers
from .creator import api_key, balance, marketplace, works

# Import datasets controllers
from .datasets import (
    data_source,
    datasets,
    datasets_document,
    datasets_segments,
    external,
    hit_testing,
    metadata,
    website,
)
from .datasets.rag_pipeline import (
    datasource_auth,
    datasource_content_preview,
    rag_pipeline,
    rag_pipeline_datasets,
    rag_pipeline_draft_variable,
    rag_pipeline_import,
    rag_pipeline_workflow,
)

# Import explore controllers
from .explore import (
    banner,
    installed_app,
    parameter,
    recommended_app,
    saved_message,
    trial,
)

# Import tag controllers
from .tag import tags

# Import workspace controllers
from .workspace import (
    account,
    agent_providers,
    endpoint,
    load_balancing_config,
    members,
    model_providers,
    models,
    plugin,
    tool_providers,
    topup,
    trigger_providers,
    workspace,
)

api.add_namespace(console_ns)

__all__ = [
    "account",
    "activate",
    "admin",
    "advanced_prompt_template",
    "agent",
    "agent_providers",
    "annotation",
    "api",
    "apikey",
    "app",
    "audio",
    "banner",
    "billing",
    "bp",
    "completion",
    "compliance",
    "console_ns",
    "conversation",
    "conversation_variables",
    "data_source",
    "data_source_bearer_auth",
    "data_source_oauth",
    "datasets",
    "datasets_document",
    "datasets_segments",
    "datasource_auth",
    "datasource_content_preview",
    "email_register",
    "endpoint",
    "extension",
    "external",
    "feature",
    "forgot_password",
    "generator",
    "hit_testing",
    "human_input_form",
    "init_validate",
    "installed_app",
    "load_balancing_config",
    "login",
    "mcp_server",
    "members",
    "message",
    "metadata",
    "model_config",
    "model_providers",
    "models",
    "notification",
    "oauth",
    "oauth_server",
    "ops_trace",
    "parameter",
    "ping",
    "plugin",
    "rag_pipeline",
    "rag_pipeline_datasets",
    "rag_pipeline_draft_variable",
    "rag_pipeline_import",
    "rag_pipeline_workflow",
    "recommended_app",
    "saved_message",
    "setup",
    "site",
    "spec",
    "statistic",
    "tags",
    "tool_providers",
    "topup",
    "trial",
    "trigger_providers",
    "version",
    "website",
    "workflow",
    "workflow_app_log",
    "workflow_draft_variable",
    "workflow_run",
    "workflow_statistic",
    "workflow_trigger",
    "workspace",
]
