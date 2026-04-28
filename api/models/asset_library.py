"""Asset library model.

Stores tenant-shared reusable assets — images, audio, video, and prompt
templates — that creators can pick from when authoring chatflows or social
publishing payloads. File-type assets reference ``upload_files.id`` via
``upload_file_id`` (no FK constraint, by Dify convention). Prompt-type assets
store text inline in ``content`` and a list of variable specs in
``prompt_variables``.

Tenant isolation is enforced at the service layer; the DB-level invariant
is just that ``tenant_id`` is non-null on every row, and the composite
``(tenant_id, asset_type, created_at)`` index serves the dominant list query.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import TypeBase
from .types import AdjustedJSON, StringUUID


class AssetLibrary(TypeBase):
    """A reusable asset belonging to a tenant.

    Two flavours coexist on the same row to keep the management surface
    uniform:

    - **File-type** (``asset_type`` in {image, audio, video}): metadata only;
      the binary lives in ``upload_files`` and is referenced via
      ``upload_file_id``. Media-specific fields (``cover_url``, ``duration``,
      ``width``, ``height``, ``file_size``) are populated by the metadata
      extractor at create time.
    - **Prompt-type** (``asset_type`` == "prompt"): inline text in
      ``content`` plus a JSON list of variable specs in ``prompt_variables``.
      File-only fields stay null.

    The ``tags`` array is a free-form string list, ``category`` is a single
    optional bucket name. Both default to safe empty values so list/filter
    queries can rely on non-null columns.
    """

    __tablename__ = "asset_libraries"
    __table_args__ = (
        sa.PrimaryKeyConstraint("id", name="asset_library_pkey"),
        sa.Index("idx_asset_lib_tenant_type_created", "tenant_id", "asset_type", "created_at"),
        sa.Index("idx_asset_lib_tenant_id", "tenant_id"),
        sa.Index("idx_asset_lib_category", "category"),
    )

    id: Mapped[str] = mapped_column(
        StringUUID,
        server_default=func.gen_random_uuid(),
        insert_default=lambda: str(uuid4()),
        default_factory=lambda: str(uuid4()),
        init=False,
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    created_by: Mapped[str] = mapped_column(StringUUID, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True, default=None)
    tags: Mapped[list[Any]] = mapped_column(
        AdjustedJSON(astext_type=Text()),
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default_factory=list,
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    upload_file_id: Mapped[str | None] = mapped_column(StringUUID, nullable=True, default=None)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    duration: Mapped[float | None] = mapped_column(Float(), nullable=True, default=None)
    width: Mapped[int | None] = mapped_column(Integer(), nullable=True, default=None)
    height: Mapped[int | None] = mapped_column(Integer(), nullable=True, default=None)
    file_size: Mapped[int | None] = mapped_column(BigInteger(), nullable=True, default=None)
    content: Mapped[str | None] = mapped_column(Text(), nullable=True, default=None)
    prompt_variables: Mapped[list[Any]] = mapped_column(
        AdjustedJSON(astext_type=Text()),
        nullable=False,
        server_default=text("'[]'::jsonb"),
        default_factory=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        init=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        init=False,
    )

    def __repr__(self) -> str:
        return f"<AssetLibrary id={self.id} tenant={self.tenant_id} type={self.asset_type} name={self.name!r}>"
