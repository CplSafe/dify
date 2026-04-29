"""Unit tests for the asset-library file-upload controller.

Mirrors the auth-decorator-noop reload pattern used by
``test_assets_controller.py``: auth decorators are replaced with identity
functions and ``console_ns.route`` is neutralized so importing the module
doesn't collide with the real blueprint registry. The Resource subclass is
then instantiated directly and its method invoked inside an
``app.test_request_context`` block built from a multipart ``EnvironBuilder``.
"""

from __future__ import annotations

import builtins
import importlib
import json
import sys
from datetime import datetime
from io import BytesIO
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.views import MethodView
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
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

from services.errors.asset_library import (
    FileSizeLimitExceededError,
    UnsupportedMimeTypeError,
)
from services.errors.file import FileTooLargeError, UnsupportedFileTypeError

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
def files_module(monkeypatch: pytest.MonkeyPatch):
    """Reload the file-upload controller with auth decorators and the
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

    module_name = "controllers.console.asset_library.files"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _make_asset(
    *,
    asset_id: str = "asset-1",
    tenant_id: str = "tenant-1",
    asset_type: str = "image",
    name: str = "test",
    created_by: str = "user-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=asset_id,
        tenant_id=tenant_id,
        asset_type=asset_type,
        name=name,
        description=None,
        tags=[],
        category=None,
        upload_file_id="upload-1",
        cover_url=None,
        signed_url=None,
        duration=None,
        width=10,
        height=10,
        file_size=128,
        content=None,
        prompt_variables=None,
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


def _stubattach_creator(module, monkeypatch):
    if hasattr(module, "attach_creator"):
        monkeypatch.setattr(module, "attach_creator", lambda asset: asset)
    else:
        monkeypatch.setattr(module, "prepare_asset_response", lambda asset: asset)


def _stub_prepare_asset_response_internals(module, monkeypatch):
    """Keep response preparation real while avoiding the creator DB lookup."""
    monkeypatch.setitem(module.prepare_asset_response.__globals__, "attach_creator", lambda asset: asset)


def _multipart_env(
    *,
    file_field: tuple[bytes, str, str] | None = ("fake-bytes", "test.png", "image/png"),
    asset_type: str | None = "image",
    name: str | None = None,
    description: str | None = None,
    category: str | None = None,
    tags: str | None = None,
    omit_file: bool = False,
):
    """Build a Werkzeug environ for a POST multipart form."""
    data: dict = {}
    if not omit_file and file_field is not None:
        payload, filename, content_type = file_field
        data["file"] = (BytesIO(payload if isinstance(payload, bytes) else payload.encode()), filename, content_type)
    if asset_type is not None:
        data["asset_type"] = asset_type
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description
    if category is not None:
        data["category"] = category
    if tags is not None:
        data["tags"] = tags
    builder = EnvironBuilder(
        method="POST",
        path="/asset-library/files",
        data=data,
        content_type="multipart/form-data",
    )
    return builder.get_environ()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestAssetFileUploadHappyPath:
    def test_returns_201_and_forwards_kwargs_to_service(self, flask_app, files_module, monkeypatch):
        account = _install_current_account(files_module, monkeypatch)
        _stubattach_creator(files_module, monkeypatch)
        asset = _make_asset(name="测试图")
        captured: dict = {}

        def _create(**kwargs):
            captured.update(kwargs)
            return asset

        monkeypatch.setattr(
            files_module.AssetLibraryService,
            "create_file_asset",
            staticmethod(_create),
        )

        env = _multipart_env(
            file_field=(b"png-bytes", "test.png", "image/png"),
            asset_type="image",
            name="测试图",
            tags=json.dumps(["a", "b"]),
        )

        with flask_app.request_context(env):
            body, status = files_module.AssetFileUploadApi().post()

        assert status == 201
        assert body is asset
        assert captured["tenant_id"] == "tenant-1"
        assert captured["user"] is account
        assert captured["filename"] == "test.png"
        assert captured["mimetype"] == "image/png"
        assert captured["file_content"] == b"png-bytes"
        assert captured["asset_type"] is files_module.AssetType.IMAGE
        assert captured["name"] == "测试图"
        assert captured["tags"] == ["a", "b"]
        assert captured["description"] is None
        assert captured["category"] is None

    def test_returns_signed_preview_url_for_uploaded_file(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        _stub_prepare_asset_response_internals(files_module, monkeypatch)
        asset = _make_asset(name="测试图")
        monkeypatch.setattr(
            files_module.AssetLibraryService,
            "create_file_asset",
            staticmethod(lambda **_kwargs: asset),
        )
        monkeypatch.setattr(
            files_module.prepare_asset_response.__globals__["file_helpers"],
            "get_signed_file_url",
            lambda upload_file_id, **_kwargs: f"https://files.example/{upload_file_id}",
        )

        env = _multipart_env(
            file_field=(b"png-bytes", "test.png", "image/png"),
            asset_type="image",
            name="测试图",
        )

        with flask_app.request_context(env):
            body, status = files_module.AssetFileUploadApi().post()

        assert status == 201
        assert body.signed_url == "https://files.example/upload-1"


# ---------------------------------------------------------------------------
# Validation failures (400)
# ---------------------------------------------------------------------------


class TestAssetFileUploadValidation:
    def test_missing_file_part_raises_bad_request(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        env = _multipart_env(omit_file=True, asset_type="image")

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                files_module.AssetFileUploadApi().post()

    def test_empty_filename_raises_bad_request(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        env = _multipart_env(file_field=(b"x", "", "image/png"), asset_type="image")

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                files_module.AssetFileUploadApi().post()

    def test_invalid_asset_type_raises_bad_request(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        env = _multipart_env(asset_type="video_clip")

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                files_module.AssetFileUploadApi().post()

    def test_prompt_asset_type_rejected_with_dedicated_message(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        env = _multipart_env(asset_type="prompt")

        with flask_app.request_context(env):
            with pytest.raises(BadRequest) as exc_info:
                files_module.AssetFileUploadApi().post()

        assert "/asset-library/prompts" in str(exc_info.value)

    def test_unsupported_mime_from_service_raises_bad_request(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        _stubattach_creator(files_module, monkeypatch)

        def _create(**_kwargs):
            raise UnsupportedMimeTypeError("video/avi")

        monkeypatch.setattr(
            files_module.AssetLibraryService,
            "create_file_asset",
            staticmethod(_create),
        )

        env = _multipart_env(
            file_field=(b"avi-bytes", "test.avi", "video/avi"),
            asset_type="video",
        )

        with flask_app.request_context(env):
            with pytest.raises(BadRequest) as exc_info:
                files_module.AssetFileUploadApi().post()

        assert "video/avi" in str(exc_info.value)

    def test_malformed_tags_json_raises_bad_request(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        env = _multipart_env(asset_type="image", tags="not-json")

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                files_module.AssetFileUploadApi().post()

    def test_unsupported_file_type_from_filesvc_raises_bad_request(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        _stubattach_creator(files_module, monkeypatch)

        def _create(**_kwargs):
            raise UnsupportedFileTypeError()

        monkeypatch.setattr(
            files_module.AssetLibraryService,
            "create_file_asset",
            staticmethod(_create),
        )

        env = _multipart_env(asset_type="image")

        with flask_app.request_context(env):
            with pytest.raises(BadRequest):
                files_module.AssetFileUploadApi().post()


# ---------------------------------------------------------------------------
# Size violations (413)
# ---------------------------------------------------------------------------


class TestAssetFileUploadSizeLimit:
    def test_file_too_large_returns_413(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        _stubattach_creator(files_module, monkeypatch)

        def _create(**_kwargs):
            raise FileTooLargeError("limit exceeded")

        monkeypatch.setattr(
            files_module.AssetLibraryService,
            "create_file_asset",
            staticmethod(_create),
        )

        env = _multipart_env(asset_type="image")

        with flask_app.request_context(env):
            with pytest.raises(RequestEntityTooLarge):
                files_module.AssetFileUploadApi().post()

    def test_asset_library_size_limit_returns_413(self, flask_app, files_module, monkeypatch):
        _install_current_account(files_module, monkeypatch)
        _stubattach_creator(files_module, monkeypatch)

        def _create(**_kwargs):
            raise FileSizeLimitExceededError("over the cap")

        monkeypatch.setattr(
            files_module.AssetLibraryService,
            "create_file_asset",
            staticmethod(_create),
        )

        env = _multipart_env(asset_type="image")

        with flask_app.request_context(env):
            with pytest.raises(RequestEntityTooLarge):
                files_module.AssetFileUploadApi().post()
