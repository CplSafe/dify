"""Unit tests for the asset-library prompt-creation controller.

Mirrors the auth-decorator-noop reload pattern used by
``test_files_controller.py``: auth decorators are replaced with identity
functions and ``console_ns.route`` is neutralized so importing the module
doesn't collide with the real blueprint registry. The Resource subclass is
then instantiated directly and its method invoked inside an
``app.test_request_context`` block built from a JSON ``EnvironBuilder``.
"""

from __future__ import annotations

import builtins
import importlib
import json
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.views import MethodView
from werkzeug.exceptions import BadRequest
from werkzeug.test import EnvironBuilder

# Some local dev environments ship an incomplete ``alipay`` namespace package
# (no top-level ``AliPay`` export). Stub it before any controller import so the
# test is portable. CI installs the real package and this branch is a no-op.
try:
    from alipay import AliPay  # type: ignore[import-untyped]  # noqa: F401
except ImportError:  # pragma: no cover - environment-dependent
    _stub = ModuleType("alipay")
    _stub.AliPay = type("AliPay", (), {})  # type: ignore[attr-defined]
    _stub.ISVAliPay = type("ISVAliPay", (), {})  # type: ignore[attr-defined]
    _stub.AliPayISV = _stub.ISVAliPay  # type: ignore[attr-defined]
    sys.modules["alipay"] = _stub

from services.errors.asset_library import InvalidPromptVariablesError

# flask_restx historically expected a top-level ``MethodView`` symbol. Some
# Flask versions used in this repo don't expose it; mirror the workaround.
if not hasattr(builtins, "MethodView"):
    builtins.MethodView = MethodView  # type: ignore[attr-defined]


@pytest.fixture
def flask_app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def prompts_module(monkeypatch: pytest.MonkeyPatch):
    """Reload the prompt-create controller with auth decorators and the
    namespace route neutralised so the module imports without touching the
    real console blueprint."""
    from controllers.console import console_ns
    from controllers.console import wraps as console_wraps
    from libs import login as login_module

    def _noop(func):
        return func

    monkeypatch.setattr(login_module, "login_required", _noop)
    monkeypatch.setattr(console_wraps, "setup_required", _noop)
    monkeypatch.setattr(console_wraps, "account_initialization_required", _noop)

    def _noop_route(*_args, **_kwargs):
        def _decorator(cls):
            return cls

        return _decorator

    monkeypatch.setattr(console_ns, "route", _noop_route)
    # ``marshal_with`` is applied at decoration time. Replace it with a
    # pass-through so the test asserts the dict the handler builds, not the
    # post-marshal output (which would require a full Flask response context
    # to resolve nested fields).
    monkeypatch.setattr(console_ns, "marshal_with", lambda *_a, **_kw: _noop)

    module_name = "controllers.console.asset_library.prompts"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _make_asset(
    *,
    asset_id: str = "asset-1",
    tenant_id: str = "tenant-1",
    name: str = "种草",
    created_by: str = "user-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=asset_id,
        tenant_id=tenant_id,
        asset_type="prompt",
        name=name,
        description=None,
        tags=[],
        category=None,
        upload_file_id=None,
        cover_url=None,
        signed_url=None,
        duration=None,
        width=None,
        height=None,
        file_size=None,
        content="x",
        prompt_variables=[],
        created_by=created_by,
        created_at=datetime(2026, 4, 28, 12, 0, 0),
        updated_at=datetime(2026, 4, 28, 12, 0, 0),
    )


def _install_current_account(module, monkeypatch, tenant_id: str = "tenant-1"):
    account = MagicMock()
    account.id = "user-1"
    account.current_tenant_id = tenant_id
    monkeypatch.setattr(module, "current_account_with_tenant", lambda: (account, tenant_id))
    return account


def _stub_attach_creator(module, monkeypatch):
    monkeypatch.setattr(module, "_attach_creator", lambda asset: asset)


def _json_env(payload):
    """Build a Werkzeug environ for a POST application/json request.

    ``payload`` may be a dict (encoded via ``json.dumps``) or a raw string for
    malformed-body coverage.
    """
    if isinstance(payload, str):
        body = payload
    else:
        body = json.dumps(payload)
    builder = EnvironBuilder(
        method="POST",
        path="/asset-library/prompts",
        data=body,
        content_type="application/json",
    )
    return builder.get_environ()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestAssetPromptCreateHappyPath:
    def test_returns_201_and_forwards_kwargs_to_service(self, flask_app, prompts_module, monkeypatch):
        account = _install_current_account(prompts_module, monkeypatch)
        _stub_attach_creator(prompts_module, monkeypatch)
        asset = _make_asset(name="种草")
        captured: dict = {}

        def _create(**kwargs):
            captured.update(kwargs)
            return asset

        monkeypatch.setattr(
            prompts_module.AssetLibraryService,
            "create_prompt_asset",
            staticmethod(_create),
        )

        env = _json_env(
            {
                "name": "种草",
                "content": "x",
                "prompt_variables": [{"name": "a", "type": "string"}],
                "tags": ["a", "b"],
                "description": "test desc",
                "category": "test cat",
            }
        )

        with flask_app.request_context(env):
            body, status = prompts_module.AssetPromptCreateApi().post()

        assert status == 201
        assert body is asset
        assert captured["tenant_id"] == "tenant-1"
        assert captured["user"] is account
        assert captured["name"] == "种草"
        assert captured["content"] == "x"
        assert captured["prompt_variables"] == [{"name": "a", "type": "string"}]
        assert captured["tags"] == ["a", "b"]
        assert captured["description"] == "test desc"
        assert captured["category"] == "test cat"

    def test_default_values_for_optional_fields(self, flask_app, prompts_module, monkeypatch):
        _install_current_account(prompts_module, monkeypatch)
        _stub_attach_creator(prompts_module, monkeypatch)
        asset = _make_asset()
        captured: dict = {}

        def _create(**kwargs):
            captured.update(kwargs)
            return asset

        monkeypatch.setattr(
            prompts_module.AssetLibraryService,
            "create_prompt_asset",
            staticmethod(_create),
        )

        env = _json_env({"name": "n", "content": "c"})

        with flask_app.request_context(env):
            body, status = prompts_module.AssetPromptCreateApi().post()

        assert status == 201
        assert body is asset
        assert captured["prompt_variables"] == []
        assert captured["tags"] == []
        assert captured["description"] is None
        assert captured["category"] is None


# ---------------------------------------------------------------------------
# Validation failures (400)
# ---------------------------------------------------------------------------


class TestAssetPromptCreateValidation:
    def test_missing_name_raises_bad_request(self, flask_app, prompts_module, monkeypatch):
        _install_current_account(prompts_module, monkeypatch)
        env = _json_env({"content": "x"})

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                prompts_module.AssetPromptCreateApi().post()

    def test_empty_name_raises_bad_request(self, flask_app, prompts_module, monkeypatch):
        _install_current_account(prompts_module, monkeypatch)
        env = _json_env({"name": "", "content": "x"})

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                prompts_module.AssetPromptCreateApi().post()

    def test_missing_content_raises_bad_request(self, flask_app, prompts_module, monkeypatch):
        _install_current_account(prompts_module, monkeypatch)
        env = _json_env({"name": "y"})

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                prompts_module.AssetPromptCreateApi().post()

    def test_prompt_variables_not_list_raises_bad_request(self, flask_app, prompts_module, monkeypatch):
        _install_current_account(prompts_module, monkeypatch)
        env = _json_env({"name": "y", "content": "x", "prompt_variables": "oops"})

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                prompts_module.AssetPromptCreateApi().post()

    def test_tags_not_list_raises_bad_request(self, flask_app, prompts_module, monkeypatch):
        _install_current_account(prompts_module, monkeypatch)
        env = _json_env({"name": "y", "content": "x", "tags": "oops"})

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                prompts_module.AssetPromptCreateApi().post()

    def test_invalid_prompt_variables_from_service_raises_bad_request(self, flask_app, prompts_module, monkeypatch):
        _install_current_account(prompts_module, monkeypatch)
        _stub_attach_creator(prompts_module, monkeypatch)

        def _create(**_kwargs):
            raise InvalidPromptVariablesError("duplicate variable name 'a'")

        monkeypatch.setattr(
            prompts_module.AssetLibraryService,
            "create_prompt_asset",
            staticmethod(_create),
        )

        env = _json_env(
            {
                "name": "y",
                "content": "x",
                "prompt_variables": [{"name": "a", "type": "string"}, {"name": "a", "type": "string"}],
            }
        )

        with flask_app.request_context(env):
            with pytest.raises(BadRequest) as exc_info:
                prompts_module.AssetPromptCreateApi().post()

        assert "duplicate variable name 'a'" in str(exc_info.value)
