"""Unit tests for the asset-library generic CRUD console endpoints.

Mirrors the auth-decorator-noop reload pattern used by
``tests/unit_tests/controllers/console/workspace/test_allocation.py``: the
auth decorators (``setup_required``, ``login_required``,
``account_initialization_required``) are replaced with identity functions
and ``console_ns.route`` is neutralized so importing the module doesn't
collide with the real blueprint registry. The Resource subclass is then
instantiated directly and its method invoked inside an
``app.test_request_context`` block.
"""

from __future__ import annotations

import builtins
import importlib
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from flask.views import MethodView
from werkzeug.exceptions import BadRequest, NotFound

# Some local dev environments ship an incomplete ``alipay`` namespace package
# (no top-level ``AliPay`` export), which breaks ``from alipay import AliPay``
# inside ``services.payment.alipay_client`` during ``controllers.console``
# import. We stub it here before any controller-side import runs so the test
# is portable. CI installs the full package and this branch is a no-op.
try:
    from alipay import AliPay  # type: ignore[import-untyped]  # noqa: F401
except ImportError:  # pragma: no cover - environment-dependent
    _stub = ModuleType("alipay")
    _stub.AliPay = type("AliPay", (), {})  # type: ignore[attr-defined]
    _stub.ISVAliPay = type("ISVAliPay", (), {})  # type: ignore[attr-defined]
    _stub.AliPayISV = _stub.ISVAliPay  # type: ignore[attr-defined]
    sys.modules["alipay"] = _stub

from services.asset_library_service import AssetPage
from services.errors.asset_library import (
    AssetNotFoundError,
    InvalidPromptVariablesError,
)

# flask_restx historically expected a top-level ``MethodView`` symbol. Some
# Flask versions used in this repo don't expose it; mirror the workaround
# from ``test_allocation.py``.
if not hasattr(builtins, "MethodView"):
    builtins.MethodView = MethodView  # type: ignore[attr-defined]


@pytest.fixture
def flask_app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def assets_module(monkeypatch: pytest.MonkeyPatch):
    """Reload the assets controller with auth decorators and the namespace
    route neutralised so the module imports without touching the real
    console blueprint."""
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
    # pass-through so the test asserts the dict the handler builds, not
    # the post-marshal output (which would require a real Flask response
    # context for ``Nested`` resolution).
    monkeypatch.setattr(console_ns, "marshal_with", lambda *_a, **_kw: _noop)

    module_name = "controllers.console.asset_library.assets"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _make_asset(
    *,
    asset_id: str = "asset-1",
    tenant_id: str = "tenant-1",
    asset_type: str = "prompt",
    name: str = "Greeting",
    created_by: str = "user-1",
) -> SimpleNamespace:
    """Build an ``AssetLibrary``-shaped stub. ``attach_creator`` mutates
    ``created_by`` so we use ``SimpleNamespace`` (mutable) instead of a
    frozen dataclass."""
    return SimpleNamespace(
        id=asset_id,
        tenant_id=tenant_id,
        asset_type=asset_type,
        name=name,
        description="d",
        tags=[],
        category=None,
        upload_file_id=None,
        cover_url=None,
        signed_url=None,
        duration=None,
        width=None,
        height=None,
        file_size=None,
        content="hi",
        prompt_variables=[],
        created_by=created_by,
        created_at=datetime(2026, 4, 28, 12, 0, 0),
        updated_at=datetime(2026, 4, 28, 12, 0, 0),
    )


def _install_current_account(module, monkeypatch, tenant_id: str = "tenant-1"):
    account = MagicMock()
    account.id = "user-1"
    monkeypatch.setattr(module, "current_account_with_tenant", lambda: (account, tenant_id))


def _stubattach_creator(module, monkeypatch):
    """Skip the DB lookup that ``attach_creator`` would otherwise perform."""
    monkeypatch.setattr(module, "attach_creator", lambda asset: asset)


# ---------------------------------------------------------------------------
# GET /asset-library
# ---------------------------------------------------------------------------


class TestAssetList:
    def test_returns_paginated_envelope(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        _stubattach_creator(assets_module, monkeypatch)
        asset = _make_asset()
        page = AssetPage(items=[asset], total=1, page=1, limit=20)
        captured: dict = {}

        def _list(**kwargs):
            captured.update(kwargs)
            return page

        monkeypatch.setattr(assets_module.AssetLibraryService, "list_assets", staticmethod(_list))

        with flask_app.test_request_context("/asset-library?type=prompt&page=2&limit=10"):
            body = assets_module.AssetListApi().get()

        assert body["total"] == 1
        assert body["page"] == 1
        assert body["limit"] == 20
        assert body["has_more"] is False
        assert body["data"] == [asset]
        # ``page=2&limit=10`` query args should reach the service.
        assert captured["page"] == 2
        assert captured["limit"] == 10
        assert captured["asset_type"] == "prompt"
        assert captured["tenant_id"] == "tenant-1"

    def test_file_assets_include_signed_preview_url(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        _stubattach_creator(assets_module, monkeypatch)
        asset = _make_asset(asset_type="image")
        asset.upload_file_id = "upload-1"
        page = AssetPage(items=[asset], total=1, page=1, limit=20)
        monkeypatch.setattr(
            assets_module.AssetLibraryService,
            "list_assets",
            staticmethod(lambda **kwargs: page),
        )
        monkeypatch.setattr(
            assets_module.file_helpers,
            "get_signed_file_url",
            lambda upload_file_id, **_kwargs: f"https://files.example/{upload_file_id}",
        )

        with flask_app.test_request_context("/asset-library"):
            body = assets_module.AssetListApi().get()

        assert body["data"][0].signed_url == "https://files.example/upload-1"

    def test_has_more_true_when_more_pages_remain(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        _stubattach_creator(assets_module, monkeypatch)
        page = AssetPage(items=[_make_asset()], total=50, page=1, limit=20)
        monkeypatch.setattr(
            assets_module.AssetLibraryService,
            "list_assets",
            staticmethod(lambda **kwargs: page),
        )

        with flask_app.test_request_context("/asset-library"):
            body = assets_module.AssetListApi().get()

        assert body["has_more"] is True


# ---------------------------------------------------------------------------
# GET /asset-library/<id>
# ---------------------------------------------------------------------------


class TestAssetDetail:
    def test_returns_asset_with_creator_attached(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        _stubattach_creator(assets_module, monkeypatch)
        asset = _make_asset()
        captured: dict = {}

        def _get(tenant_id, asset_id):
            captured["tenant_id"] = tenant_id
            captured["asset_id"] = asset_id
            return asset

        monkeypatch.setattr(assets_module.AssetLibraryService, "get_asset", staticmethod(_get))

        with flask_app.test_request_context("/asset-library/asset-1"):
            result = assets_module.AssetDetailApi().get("asset-1")

        assert result is asset
        assert captured == {"tenant_id": "tenant-1", "asset_id": "asset-1"}

    def test_file_asset_detail_includes_signed_preview_url(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        _stubattach_creator(assets_module, monkeypatch)
        asset = _make_asset(asset_type="image")
        asset.upload_file_id = "upload-1"
        monkeypatch.setattr(assets_module.AssetLibraryService, "get_asset", staticmethod(lambda *_args: asset))
        monkeypatch.setattr(
            assets_module.file_helpers,
            "get_signed_file_url",
            lambda upload_file_id, **_kwargs: f"https://files.example/{upload_file_id}",
        )

        with flask_app.test_request_context("/asset-library/asset-1"):
            result = assets_module.AssetDetailApi().get("asset-1")

        assert result.signed_url == "https://files.example/upload-1"

    def test_missing_asset_raises_not_found(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        _stubattach_creator(assets_module, monkeypatch)

        def _get(_tenant_id, _asset_id):
            raise AssetNotFoundError("nope")

        monkeypatch.setattr(assets_module.AssetLibraryService, "get_asset", staticmethod(_get))

        with flask_app.test_request_context("/asset-library/asset-x"):
            with pytest.raises(NotFound):
                assets_module.AssetDetailApi().get("asset-x")


# ---------------------------------------------------------------------------
# PATCH /asset-library/<id>
# ---------------------------------------------------------------------------


class TestAssetPatch:
    def test_forwards_whitelisted_fields_to_service(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        _stubattach_creator(assets_module, monkeypatch)
        asset = _make_asset(name="Updated")
        captured: dict = {}

        def _update(**kwargs):
            captured.update(kwargs)
            return asset

        monkeypatch.setattr(
            assets_module.AssetLibraryService,
            "update_asset_metadata",
            staticmethod(_update),
        )

        body = {"name": "Updated", "description": "d2", "asset_type": "ignored"}
        with flask_app.test_request_context(
            "/asset-library/asset-1",
            method="PATCH",
            json=body,
        ):
            result = assets_module.AssetDetailApi().patch("asset-1")

        assert result is asset
        assert captured["tenant_id"] == "tenant-1"
        assert captured["asset_id"] == "asset-1"
        assert captured["name"] == "Updated"
        assert captured["description"] == "d2"
        # Black-listed body keys must not leak into the service call.
        assert "asset_type" not in captured

    def test_invalid_prompt_variables_returns_bad_request(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        _stubattach_creator(assets_module, monkeypatch)

        def _update(**_kwargs):
            raise InvalidPromptVariablesError("bad schema")

        monkeypatch.setattr(
            assets_module.AssetLibraryService,
            "update_asset_metadata",
            staticmethod(_update),
        )

        with flask_app.test_request_context(
            "/asset-library/asset-1",
            method="PATCH",
            json={"prompt_variables": [{"bogus": True}]},
        ):
            with pytest.raises(BadRequest):
                assets_module.AssetDetailApi().patch("asset-1")

    def test_missing_asset_raises_not_found(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        _stubattach_creator(assets_module, monkeypatch)

        def _update(**_kwargs):
            raise AssetNotFoundError("missing")

        monkeypatch.setattr(
            assets_module.AssetLibraryService,
            "update_asset_metadata",
            staticmethod(_update),
        )

        with flask_app.test_request_context(
            "/asset-library/asset-x",
            method="PATCH",
            json={"name": "x"},
        ):
            with pytest.raises(NotFound):
                assets_module.AssetDetailApi().patch("asset-x")


# ---------------------------------------------------------------------------
# DELETE /asset-library/<id>
# ---------------------------------------------------------------------------


class TestAssetDelete:
    def test_returns_204_and_calls_service(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)
        captured: dict = {}

        def _delete(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(
            assets_module.AssetLibraryService,
            "delete_asset",
            staticmethod(_delete),
        )

        with flask_app.test_request_context("/asset-library/asset-1", method="DELETE"):
            body, status = assets_module.AssetDetailApi().delete("asset-1")

        assert status == 204
        assert body == ""
        assert captured == {"tenant_id": "tenant-1", "asset_id": "asset-1"}

    def test_missing_asset_raises_not_found(self, flask_app, assets_module, monkeypatch):
        _install_current_account(assets_module, monkeypatch)

        def _delete(**_kwargs):
            raise AssetNotFoundError("missing")

        monkeypatch.setattr(
            assets_module.AssetLibraryService,
            "delete_asset",
            staticmethod(_delete),
        )

        with flask_app.test_request_context("/asset-library/asset-x", method="DELETE"):
            with pytest.raises(NotFound):
                assets_module.AssetDetailApi().delete("asset-x")


# ---------------------------------------------------------------------------
# attach_creator helper
# ---------------------------------------------------------------------------


class TestAttachCreator:
    def test_resolves_uuid_to_account_dict(self, assets_module, monkeypatch):
        asset = _make_asset(created_by="user-1")
        account = SimpleNamespace(id="user-1", name="Alice", avatar="alice.png")

        class _FakeSession:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def execute(self, _stmt):
                result = MagicMock()
                result.scalar_one_or_none.return_value = account
                return result

        monkeypatch.setattr(assets_module, "Session", _FakeSession)
        monkeypatch.setattr(assets_module, "db", SimpleNamespace(engine=object()))

        result = assets_module.attach_creator(asset)

        assert result.created_by == {"id": "user-1", "name": "Alice", "avatar": "alice.png"}

    def test_unknown_account_sets_none(self, assets_module, monkeypatch):
        asset = _make_asset(created_by="ghost-user")

        class _FakeSession:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def execute(self, _stmt):
                result = MagicMock()
                result.scalar_one_or_none.return_value = None
                return result

        monkeypatch.setattr(assets_module, "Session", _FakeSession)
        monkeypatch.setattr(assets_module, "db", SimpleNamespace(engine=object()))

        result = assets_module.attach_creator(asset)

        assert result.created_by is None

    def test_already_attached_creator_is_returned_unchanged(self, assets_module):
        creator = {"id": "user-1", "name": "Alice", "avatar": None}
        asset = _make_asset()
        asset.created_by = creator  # type: ignore[assignment]

        result = assets_module.attach_creator(asset)

        assert result.created_by is creator
