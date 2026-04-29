"""Asset Library generic CRUD endpoints.

Routes (all under /console/api):

- GET    /asset-library                     paginated tenant-scoped list
- GET    /asset-library/<asset_id>          single asset detail
- PATCH  /asset-library/<asset_id>          update whitelist metadata fields
- DELETE /asset-library/<asset_id>          delete asset (cascades file cleanup)

The two creation routes (POST /asset-library/files for multipart uploads
and POST /asset-library/prompts for JSON) live in sibling modules so the
content-type-specific parsing stays separate.

The model only stores ``created_by`` as a UUID string; the response
serializer expects an ``Account``-shaped ``{id, name, avatar}`` dict
(see ``fields.asset_library_fields.asset_creator_fields``). The
``prepare_asset_response`` helper performs that lookup before marshalling and
also materializes transient signed preview URLs from stored ``upload_file_id``
references. The database row never stores these signed URLs.
"""

from __future__ import annotations

from typing import Any

from flask import request
from flask_restx import Resource
from graphon.file import helpers as file_helpers
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.exceptions import BadRequest, NotFound

from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
)
from extensions.ext_database import db
from fields.asset_library_fields import asset_fields, asset_pagination_fields
from libs.login import current_account_with_tenant, login_required
from models import Account
from models.asset_library import AssetLibrary
from services.asset_library_service import AssetLibraryService
from services.errors.asset_library import (
    AssetNotFoundError,
    InvalidPromptVariablesError,
)


def attach_creator(asset: AssetLibrary) -> AssetLibrary:
    """Resolve ``asset.created_by`` UUID to an ``Account``-shaped dict.

    The ORM column stores the creator's UUID. ``asset_fields`` declares
    ``created_by`` as ``Nested(asset_creator_fields)`` which expects an
    object exposing ``id`` / ``name`` / ``avatar``. This helper mutates
    the in-memory instance only — the session has already been committed
    so the change is never written back. Returns ``asset`` unchanged when
    ``created_by`` is missing or already attached.

    TODO(asset-library): batch-load accounts in ``list_assets`` once page
    sizes routinely exceed N=20; current N+1 is acceptable for the bounded
    page limit the service enforces.
    """
    creator = getattr(asset, "created_by", None)
    if not isinstance(creator, str):
        return asset
    creator_id = creator
    with Session(db.engine, expire_on_commit=False) as session:
        account = session.execute(select(Account).where(Account.id == creator_id)).scalar_one_or_none()
    if account is None:
        asset.created_by = None  # type: ignore[assignment]
    else:
        asset.created_by = {  # type: ignore[assignment]
            "id": account.id,
            "name": account.name,
            "avatar": getattr(account, "avatar", None),
        }
    return asset


def attach_file_urls(asset: AssetLibrary) -> AssetLibrary:
    """Materialize transient file preview URLs before marshalling.

    File assets persist only ``upload_file_id``. The API contract exposes
    ``signed_url`` so browsers can render the media immediately. Video cover
    extraction stores sibling cover files as ``cover_url="upload_file_id:<id>"``;
    resolve that internal reference to a signed URL as well.
    """
    upload_file_id = getattr(asset, "upload_file_id", None)
    if isinstance(upload_file_id, str) and upload_file_id:
        asset.signed_url = file_helpers.get_signed_file_url(upload_file_id=upload_file_id)  # type: ignore[attr-defined]

    cover_url = getattr(asset, "cover_url", None)
    if isinstance(cover_url, str) and cover_url.startswith("upload_file_id:"):
        cover_upload_file_id = cover_url.removeprefix("upload_file_id:")
        if cover_upload_file_id:
            asset.cover_url = file_helpers.get_signed_file_url(  # type: ignore[assignment]
                upload_file_id=cover_upload_file_id
            )

    return asset


def prepare_asset_response(asset: AssetLibrary) -> AssetLibrary:
    """Attach transient response-only fields expected by ``asset_fields``."""
    return attach_file_urls(attach_creator(asset))


def _patch_args() -> dict[str, Any]:
    """Whitelist body fields for PATCH /asset-library/<asset_id>.

    Mirrors ``AssetLibraryService.update_asset_metadata``'s ``_UPDATABLE_FIELDS``
    so unknown keys are silently dropped at the controller boundary instead
    of leaking through to the service.
    """
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise BadRequest("request body must be a JSON object")
    allowed = {"name", "description", "tags", "category", "content", "prompt_variables"}
    return {k: v for k, v in body.items() if k in allowed}


@console_ns.route("/asset-library")
class AssetListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.marshal_with(asset_pagination_fields)
    def get(self):
        """List tenant-scoped assets with optional filters.

        Query params (all optional except where noted):
        - ``type``        prompt | image | audio | video
        - ``keyword``     case-insensitive ``ILIKE`` match against name + description
        - ``category``    exact match
        - ``tags``        repeatable; row must contain every requested tag
        - ``page``        1-based; defaults to 1
        - ``limit``       1..100; defaults to 20

        ``page`` / ``limit`` defaults match the service-side clamp so callers
        get sane behavior even if they omit the params entirely.
        """
        _, tenant_id = current_account_with_tenant()
        asset_type = request.args.get("type") or None
        keyword = request.args.get("keyword") or None
        category = request.args.get("category") or None
        tags_args = request.args.getlist("tags") or None
        try:
            page_arg = max(1, int(request.args.get("page", 1)))
        except (TypeError, ValueError):
            page_arg = 1
        try:
            limit_arg = max(1, min(int(request.args.get("limit", 20)), 100))
        except (TypeError, ValueError):
            limit_arg = 20

        page = AssetLibraryService.list_assets(
            tenant_id=tenant_id,
            asset_type=asset_type,
            keyword=keyword,
            tags=tags_args,
            category=category,
            page=page_arg,
            limit=limit_arg,
        )
        items = [prepare_asset_response(item) for item in page.items]
        return {
            "data": items,
            "total": page.total,
            "page": page.page,
            "limit": page.limit,
            "has_more": page.has_more,
        }


@console_ns.route("/asset-library/<string:asset_id>")
class AssetDetailApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.marshal_with(asset_fields)
    def get(self, asset_id: str):
        """Fetch a single asset for the current tenant."""
        _, tenant_id = current_account_with_tenant()
        try:
            asset = AssetLibraryService.get_asset(tenant_id, asset_id)
        except AssetNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        return prepare_asset_response(asset)

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.marshal_with(asset_fields)
    def patch(self, asset_id: str):
        """Update whitelist metadata fields on an existing asset."""
        _, tenant_id = current_account_with_tenant()
        body = _patch_args()
        try:
            asset = AssetLibraryService.update_asset_metadata(
                tenant_id=tenant_id,
                asset_id=asset_id,
                **body,
            )
        except AssetNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except InvalidPromptVariablesError as exc:
            raise BadRequest(str(exc)) from exc
        return prepare_asset_response(asset)

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, asset_id: str):
        """Delete an asset (cascades upload_files cleanup for file types)."""
        _, tenant_id = current_account_with_tenant()
        try:
            AssetLibraryService.delete_asset(tenant_id=tenant_id, asset_id=asset_id)
        except AssetNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        return "", 204
