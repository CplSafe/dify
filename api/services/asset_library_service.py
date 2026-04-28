"""Asset Library service.

Tenant-shared CRUD for the ``asset_libraries`` table. All public methods take
``tenant_id`` as the first argument; queries are scoped end-to-end by
``tenant_id`` so cross-tenant access yields ``AssetNotFoundError`` rather
than returning the row.

File assets reuse ``services.file_service.FileService.upload_file`` (added in
later tasks) and store an ``upload_file_id`` reference. Prompt assets store
text inline in ``content`` and a list of variable specs in ``prompt_variables``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import cast, select
from sqlalchemy import func as sa_func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from extensions.ext_database import db
from models import Account
from models.asset_library import AssetLibrary
from services.asset_library.constants import AssetType, is_mime_allowed
from services.asset_library.metadata_extractor import (
    extract_audio_metadata,
    extract_image_metadata,
    extract_video_cover,
    extract_video_metadata,
)
from services.asset_library.schemas import PromptVariableList
from services.errors.asset_library import (
    AssetNotFoundError,
    InvalidPromptVariablesError,
    UnsupportedMimeTypeError,
)
from services.file_service import FileService

logger = logging.getLogger(__name__)


_UPDATABLE_FIELDS = frozenset({"name", "description", "tags", "category", "content", "prompt_variables"})


@dataclass(frozen=True)
class AssetPage:
    """Read-only pagination envelope returned by ``list_assets``."""

    items: list[AssetLibrary]
    total: int
    page: int
    limit: int

    @property
    def has_more(self) -> bool:
        return self.page * self.limit < self.total


class AssetLibraryService:
    """Static-method service for asset-library use cases.

    All methods are stateless and take ``tenant_id`` explicitly; the service
    layer is the single place where tenant isolation is enforced.
    """

    @staticmethod
    def create_prompt_asset(
        *,
        tenant_id: str,
        user: Account,
        name: str,
        content: str,
        prompt_variables: list[dict[str, Any]],
        description: str | None,
        tags: list[str],
        category: str | None,
    ) -> AssetLibrary:
        """Validate and persist a prompt asset.

        ``prompt_variables`` is run through :class:`PromptVariableList` so
        that controllers can rely on a single domain exception type.

        Raises:
            InvalidPromptVariablesError: ``prompt_variables`` failed schema
                validation (bad name, type/default mismatch, duplicate name).
        """
        try:
            parsed = PromptVariableList.model_validate(prompt_variables)
        except ValidationError as exc:
            raise InvalidPromptVariablesError(str(exc)) from exc

        with Session(db.engine, expire_on_commit=False) as session:
            asset = AssetLibrary(
                tenant_id=tenant_id,
                created_by=user.id,
                asset_type=AssetType.PROMPT,
                name=name,
                description=description,
                tags=list(tags),
                category=category,
                content=content,
                prompt_variables=[pv.model_dump() for pv in parsed.root],
            )
            session.add(asset)
            session.commit()
            session.refresh(asset)
            return asset

    @staticmethod
    def create_file_asset(
        *,
        tenant_id: str,
        user: Account,
        file_content: bytes,
        filename: str,
        mimetype: str,
        asset_type: AssetType,
        name: str,
        description: str | None,
        tags: list[str],
        category: str | None,
    ) -> AssetLibrary:
        """Validate, store, and persist a file-type asset (image / audio / video).

        1. Reject MIME types outside the asset-library whitelist.
        2. Delegate physical storage to ``FileService.upload_file`` so the
           asset library doesn't duplicate Dify's storage abstraction.
        3. Best-effort metadata extraction (Pillow / mutagen / ffprobe).
           Failures log at WARNING and persist NULL — the upload succeeds.
        4. For video: extract a cover frame and upload it as a sibling
           ``upload_files`` row; ``cover_url`` references its id.

        Raises:
            UnsupportedMimeTypeError: ``mimetype`` is not allowed for
                ``asset_type``.
        """
        if not is_mime_allowed(asset_type, mimetype):
            raise UnsupportedMimeTypeError(mimetype)

        file_service = FileService(db.engine)
        upload = file_service.upload_file(
            filename=filename,
            content=file_content,
            mimetype=mimetype,
            user=user,
        )

        width: int | None = None
        height: int | None = None
        duration: float | None = None
        cover_url: str | None = None

        try:
            if asset_type is AssetType.IMAGE:
                image_meta = extract_image_metadata(file_content)
                width, height = image_meta.width, image_meta.height
            elif asset_type is AssetType.AUDIO:
                duration = extract_audio_metadata(file_content).duration
            elif asset_type is AssetType.VIDEO:
                video_meta = extract_video_metadata(file_content)
                width, height, duration = video_meta.width, video_meta.height, video_meta.duration
                cover_url = _maybe_upload_video_cover(file_service, file_content, user)
        except Exception:
            logger.warning(
                "asset-library metadata extraction failed for asset_type=%s",
                asset_type,
                exc_info=True,
            )

        with Session(db.engine, expire_on_commit=False) as session:
            asset = AssetLibrary(
                tenant_id=tenant_id,
                created_by=user.id,
                asset_type=asset_type,
                name=name,
                description=description,
                tags=list(tags),
                category=category,
                upload_file_id=upload.id,
                cover_url=cover_url,
                duration=duration,
                width=width,
                height=height,
                file_size=upload.size,
            )
            session.add(asset)
            session.commit()
            session.refresh(asset)
            return asset

    @staticmethod
    def get_asset(tenant_id: str, asset_id: str) -> AssetLibrary:
        """Fetch a single asset for the tenant.

        The query is composite-scoped by ``(id, tenant_id)`` so a row that
        exists in another tenant returns ``None`` here and surfaces to the
        caller as ``AssetNotFoundError`` — never as a leaked cross-tenant
        row.

        Raises:
            AssetNotFoundError: id doesn't exist or belongs to another tenant.
        """
        with Session(db.engine, expire_on_commit=False) as session:
            stmt = select(AssetLibrary).where(
                AssetLibrary.id == asset_id,
                AssetLibrary.tenant_id == tenant_id,
            )
            asset = session.execute(stmt).scalar_one_or_none()
            if asset is None:
                raise AssetNotFoundError(f"asset {asset_id} not found")
            return asset

    @staticmethod
    def list_assets(
        *,
        tenant_id: str,
        asset_type: str | None = None,
        keyword: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> AssetPage:
        """Tenant-scoped paginated listing with optional filters.

        All filters compose with AND semantics. ``tags`` uses JSONB containment
        (one filter per tag — the row matches when its ``tags`` array contains
        every requested tag). ``page`` is clamped to ``>= 1`` and ``limit`` to
        ``[1, 100]`` so callers can't accidentally fan out unbounded queries.
        """
        page = max(page, 1)
        limit = max(min(limit, 100), 1)

        with Session(db.engine, expire_on_commit=False) as session:
            stmt = select(AssetLibrary).where(AssetLibrary.tenant_id == tenant_id)
            if asset_type:
                stmt = stmt.where(AssetLibrary.asset_type == asset_type)
            if keyword:
                kw = f"%{keyword}%"
                stmt = stmt.where(AssetLibrary.name.ilike(kw) | AssetLibrary.description.ilike(kw))
            if category:
                stmt = stmt.where(AssetLibrary.category == category)
            if tags:
                for tag in tags:
                    stmt = stmt.where(AssetLibrary.tags.op("@>")(cast([tag], JSONB)))

            count_stmt = select(sa_func.count()).select_from(stmt.subquery())
            total = session.execute(count_stmt).scalar_one()

            stmt = stmt.order_by(AssetLibrary.created_at.desc()).offset((page - 1) * limit).limit(limit)
            items = list(session.execute(stmt).scalars())
            return AssetPage(items=items, total=int(total), page=page, limit=limit)

    @staticmethod
    def update_asset_metadata(*, tenant_id: str, asset_id: str, **fields: Any) -> AssetLibrary:
        """Mutate whitelist fields on an existing asset.

        Black-listed fields (``asset_type``, ``upload_file_id``, file metadata)
        are silently dropped — clients can't change asset identity through this
        path. ``None`` values are treated as "field not provided" and skipped.

        Raises:
            AssetNotFoundError: id missing or belongs to another tenant.
            InvalidPromptVariablesError: ``prompt_variables`` payload invalid.
        """
        with Session(db.engine, expire_on_commit=False) as session:
            asset = session.get(AssetLibrary, asset_id)
            if asset is None or asset.tenant_id != tenant_id:
                raise AssetNotFoundError(f"asset {asset_id} not found")

            for key, value in fields.items():
                if key not in _UPDATABLE_FIELDS or value is None:
                    continue
                if key == "prompt_variables":
                    try:
                        parsed = PromptVariableList.model_validate(value)
                    except ValidationError as exc:
                        raise InvalidPromptVariablesError(str(exc)) from exc
                    setattr(asset, key, [pv.model_dump() for pv in parsed.root])
                elif key == "tags":
                    setattr(asset, key, list(value))
                else:
                    setattr(asset, key, value)

            session.commit()
            session.refresh(asset)
            return asset

    @staticmethod
    def delete_asset(*, tenant_id: str, asset_id: str) -> None:
        """Delete the asset row and (file types) cascade upload_files cleanup.

        Storage-side cleanup failures are logged but never abort the DB delete —
        consistent with how Dify's existing ``FileService`` treats orphaned
        blobs. Prompt-type assets skip the cleanup branch entirely.

        Raises:
            AssetNotFoundError: id missing or belongs to another tenant.
        """
        with Session(db.engine, expire_on_commit=False) as session:
            asset = session.get(AssetLibrary, asset_id)
            if asset is None or asset.tenant_id != tenant_id:
                raise AssetNotFoundError(f"asset {asset_id} not found")
            upload_file_id = asset.upload_file_id
            session.delete(asset)
            session.commit()

        if upload_file_id:
            try:
                FileService(db.engine).delete_file(upload_file_id)
            except Exception:
                logger.warning(
                    "asset-library upload_file cleanup failed for %s",
                    upload_file_id,
                    exc_info=True,
                )


def _maybe_upload_video_cover(file_service: FileService, video_bytes: bytes, user: Account) -> str | None:
    """Extract a JPEG cover from a video and upload as a sibling file.

    Returns ``None`` (logs at WARNING) when ffmpeg fails — the parent
    upload should not be aborted because of a missing thumbnail.
    """
    try:
        cover_bytes = extract_video_cover(video_bytes)
    except Exception:
        logger.warning("asset-library video cover extraction failed", exc_info=True)
        return None
    cover_upload = file_service.upload_file(
        filename="cover.jpg",
        content=cover_bytes,
        mimetype="image/jpeg",
        user=user,
    )
    return f"upload_file_id:{cover_upload.id}"
