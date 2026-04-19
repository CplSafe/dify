import re
from collections.abc import Mapping
from typing import Any

from flask import Blueprint, Flask, current_app, got_request_exception
from flask_restx import Api
from flask_restx.swagger import Swagger
from werkzeug.exceptions import HTTPException
from werkzeug.http import HTTP_STATUS_CODES

# ---------------------------------------------------------------------------
# Swagger schema generation fix
#
# Dify's controller files (and many upstream files) call fields.Nested() with
# a raw dict instead of a registered flask-restx model object, e.g.:
#
#     my_fields = {"id": fields.String, "name": fields.String}
#     result = console_ns.model("Foo", {"item": fields.Nested(my_fields)})
#
# flask-restx's Swagger.register_model() expects a Model instance and calls
# ``name not in self.api.models`` where ``name`` is ``model.name`` — but on a
# plain dict that attribute lookup returns the dict itself, making it
# unhashable and causing a TypeError that kills the entire schema render.
#
# Fix: monkey-patch Swagger.register_model to auto-wrap any raw dict it
# receives into an anonymous Model before processing. This avoids touching
# dozens of upstream controller files while still generating valid Swagger.
# ---------------------------------------------------------------------------

_orig_register_model = Swagger.register_model
_anon_model_counter: dict[int, Any] = {}  # id(dict) → Model, avoids re-wrapping


def _patched_register_model(self: Swagger, model: Any) -> None:
    if isinstance(model, dict):
        dict_id = id(model)
        if dict_id not in _anon_model_counter:
            key_sig = "_".join(sorted(str(k) for k in model))[:48]
            anon_name = f"_Anon_{key_sig}"
            # Always operate on the *real* models dict, not on any proxy
            # wrapper that may be installed by _patched_as_dict during
            # schema generation.
            real_models = getattr(self.api, "_real_models", self.api.models)
            if anon_name not in real_models:
                # Temporarily restore real models so api.model() registers
                # into the right dict.
                orig = self.api.models
                self.api.models = real_models
                try:
                    registered = self.api.model(anon_name, model)
                finally:
                    self.api.models = orig
            else:
                registered = real_models[anon_name]
            _anon_model_counter[dict_id] = registered
        model = _anon_model_counter[dict_id]
    _orig_register_model(self, model)


# Patch Swagger.as_dict: the original iterates ``self.api.models`` while
# register_model() may add new entries (our dict→model auto-wrap above).
# Replace the models dict with a snapshot-on-read proxy so the for-loop
# in the original code never sees a mutation mid-iteration.
_orig_as_dict = Swagger.as_dict


def _patched_as_dict(self: Swagger) -> dict:
    real_models = self.api.models

    from collections import UserDict

    class _SnapshotDict(UserDict):
        """UserDict subclass that returns a snapshot iterator so mutations
        during iteration are invisible to the for-loop in as_dict."""

        def __iter__(self):
            return iter(list(real_models.keys()))

        def __len__(self):
            return len(real_models)

        def __getitem__(self, key):
            return real_models[key]

        def __contains__(self, key):
            return key in real_models

        def values(self):
            return list(real_models.values())

        def items(self):
            return list(real_models.items())

    proxy = _SnapshotDict(real_models)
    # Stash real_models so _patched_register_model can find it even while
    # proxy is installed as self.api.models.
    self.api._real_models = real_models  # type: ignore[attr-defined]
    self.api.models = proxy  # type: ignore[assignment]
    try:
        return _orig_as_dict(self)
    finally:
        self.api.models = real_models
        if hasattr(self.api, "_real_models"):
            del self.api._real_models


Swagger.as_dict = _patched_as_dict  # type: ignore[method-assign]

# ---------------------------------------------------------------------------
# Patch fields.Nested.nested property
#
# When fields.Nested(some_dict) is used, self.model is the raw dict.
# The .nested property returns it as-is, and schema() then calls
# self.nested.name which raises AttributeError on a dict.
#
# We wrap the property to auto-convert any raw dict to an anonymous Model
# using the same _anon_model_counter cache used in register_model above.
# ---------------------------------------------------------------------------
from flask_restx import fields as _restx_fields
from flask_restx.model import Model as _RestxModel

_orig_nested_prop = _restx_fields.Nested.nested.fget  # type: ignore[union-attr]


def _patched_nested_fget(self: _restx_fields.Nested) -> Any:
    result = _orig_nested_prop(self)
    if not isinstance(result, dict):
        return result
    # Auto-wrap the raw dict into a named Model so .name exists.
    dict_id = id(result)
    if dict_id in _anon_model_counter:
        return _anon_model_counter[dict_id]
    key_sig = "_".join(sorted(str(k) for k in result))[:48]
    anon_name = f"_Anon_{key_sig}"
    wrapped = _RestxModel(anon_name, result)
    _anon_model_counter[dict_id] = wrapped
    return wrapped


_restx_fields.Nested.nested = property(_patched_nested_fget)  # type: ignore[assignment]


Swagger.register_model = _patched_register_model  # type: ignore[method-assign]

from configs import dify_config
from core.errors.error import AppInvokeQuotaExceededError
from libs.token import build_force_logout_cookie_headers


def http_status_message(code):
    return HTTP_STATUS_CODES.get(code, "")


def register_external_error_handlers(api: Api):
    @api.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        got_request_exception.send(current_app, exception=e)

        # If Werkzeug already prepared a Response, just use it.
        if e.response is not None:
            return e.response

        status_code = getattr(e, "code", 500) or 500

        # Build a safe, dict-like payload
        default_data = {
            "code": re.sub(r"(?<!^)(?=[A-Z])", "_", type(e).__name__).lower(),
            "message": getattr(e, "description", http_status_message(status_code)),
            "status": status_code,
        }
        if default_data["message"] == "Failed to decode JSON object: Expecting value: line 1 column 1 (char 0)":
            default_data["message"] = "Invalid JSON payload received or JSON payload is empty."

        # Use headers on the exception if present; otherwise none.
        headers = {}
        exc_headers = getattr(e, "headers", None)
        if exc_headers:
            headers.update(exc_headers)

        # Payload per status
        if status_code == 406 and api.default_mediatype is None:
            data = {"code": "not_acceptable", "message": default_data["message"], "status": status_code}
            return data, status_code, headers
        elif status_code == 400:
            msg = default_data["message"]
            if isinstance(msg, Mapping) and msg:
                # Convert param errors like {"field": "reason"} into a friendly shape
                param_key, param_value = next(iter(msg.items()))
                data = {
                    "code": "invalid_param",
                    "message": str(param_value),
                    "params": param_key,
                    "status": status_code,
                }
            else:
                data = {**default_data}
                data.setdefault("code", "unknown")
            return data, status_code, headers
        else:
            data = {**default_data}
            data.setdefault("code", "unknown")
            # If you need WWW-Authenticate for 401, add it to headers
            if status_code == 401:
                headers["WWW-Authenticate"] = 'Bearer realm="api"'
                # Check if this is a forced logout error - clear cookies
                error_code = getattr(e, "error_code", None)
                if error_code == "unauthorized_and_force_logout":
                    # Add Set-Cookie headers to clear auth cookies
                    headers["Set-Cookie"] = build_force_logout_cookie_headers()
            return data, status_code, headers

    _ = handle_http_exception

    @api.errorhandler(ValueError)
    def handle_value_error(e: ValueError):
        got_request_exception.send(current_app, exception=e)
        status_code = 400
        data = {"code": "invalid_param", "message": str(e), "status": status_code}
        return data, status_code

    _ = handle_value_error

    @api.errorhandler(AppInvokeQuotaExceededError)
    def handle_quota_exceeded(e: AppInvokeQuotaExceededError):
        got_request_exception.send(current_app, exception=e)
        status_code = 429
        data = {"code": "too_many_requests", "message": str(e), "status": status_code}
        return data, status_code

    _ = handle_quota_exceeded

    @api.errorhandler(Exception)
    def handle_general_exception(e: Exception):
        got_request_exception.send(current_app, exception=e)

        status_code = 500
        data: dict[str, Any] = getattr(e, "data", {"message": http_status_message(status_code)})

        # 🔒 Normalize non-mapping data (e.g., if someone set e.data = Response)
        if not isinstance(data, dict):
            data = {"message": str(e)}

        data.setdefault("code", "unknown")
        data.setdefault("status", status_code)

        # Note: Exception logging is handled by Flask/Flask-RESTX framework automatically
        # Explicit log_exception call removed to avoid duplicate log entries

        return data, status_code

    _ = handle_general_exception


class ExternalApi(Api):
    _authorizations = {
        "Bearer": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "Type: Bearer {your-api-key}",
        }
    }

    def __init__(self, app: Blueprint | Flask, *args, **kwargs):
        kwargs.setdefault("authorizations", self._authorizations)
        kwargs.setdefault("security", "Bearer")
        kwargs["add_specs"] = dify_config.SWAGGER_UI_ENABLED
        kwargs["doc"] = dify_config.SWAGGER_UI_PATH if dify_config.SWAGGER_UI_ENABLED else False

        # manual separate call on construction and init_app to ensure configs in kwargs effective
        super().__init__(app=None, *args, **kwargs)
        self.init_app(app, **kwargs)
        register_external_error_handlers(self)

    @property
    def base_path(self):
        # flask-restx calls url_for() to derive base_path which requires
        # SERVER_NAME to be set. Dify doesn't set SERVER_NAME, so we fall
        # back to extracting the prefix from the blueprint url_prefix instead.
        try:
            return super().base_path
        except RuntimeError:
            try:
                bp = self.app
                if hasattr(bp, "url_prefix") and bp.url_prefix:
                    return bp.url_prefix
            except Exception:  # noqa: S110
                pass
            return "/"
