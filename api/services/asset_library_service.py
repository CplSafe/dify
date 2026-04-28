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
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from extensions.ext_database import db
from models import Account
from models.asset_library import AssetLibrary
from services.asset_library.constants import AssetType
from services.asset_library.schemas import PromptVariableList
from services.errors.asset_library import (
    AssetNotFoundError,
    InvalidPromptVariablesError,
)

logger = logging.getLogger(__name__)


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
