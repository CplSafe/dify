"""add asset_libraries

Tenant-shared reusable assets — images, audio, video, prompt templates —
that creators can pick from when authoring chatflows or social publishing
payloads. File-type rows reference ``upload_files.id`` via ``upload_file_id``
(no FK, by Dify convention); prompt-type rows store text inline in
``content`` and a JSON list of variable specs in ``prompt_variables``.

Schema mirrors ``api/models/asset_library.py``. Three indexes:

- ``idx_asset_lib_tenant_type_created`` — composite, serves the dominant
  "list by tenant + type, newest first" query.
- ``idx_asset_lib_tenant_id`` — supports tenant-only counts/filters.
- ``idx_asset_lib_category`` — supports category filtering.

Revision ID: ba0600085c24
Revises: 7a1c4f9e2b03
Create Date: 2026-04-28 15:04:42.341539

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import models.types

# revision identifiers, used by Alembic.
revision = "ba0600085c24"
down_revision = "7a1c4f9e2b03"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    """Whether the bound migration context is targeting Postgres.

    Production targets Postgres; this guard exists so SQLite-backed test
    setups don't choke on the JSONB column type.
    """
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade():
    json_type: sa.types.TypeEngine
    if _is_postgres():
        json_type = postgresql.JSONB(astext_type=sa.Text())
        tags_default = sa.text("'[]'::jsonb")
        prompt_vars_default = sa.text("'[]'::jsonb")
    else:
        json_type = sa.JSON()
        tags_default = sa.text("'[]'")
        prompt_vars_default = sa.text("'[]'")

    op.create_table(
        "asset_libraries",
        sa.Column(
            "id",
            models.types.StringUUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", models.types.StringUUID(), nullable=False),
        sa.Column("created_by", models.types.StringUUID(), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "tags",
            json_type,
            nullable=False,
            server_default=tags_default,
        ),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("upload_file_id", models.types.StringUUID(), nullable=True),
        sa.Column("cover_url", sa.String(length=512), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "prompt_variables",
            json_type,
            nullable=False,
            server_default=prompt_vars_default,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="asset_library_pkey"),
    )
    # Dominant list query: tenant + asset_type, ordered by created_at.
    op.create_index(
        "idx_asset_lib_tenant_type_created",
        "asset_libraries",
        ["tenant_id", "asset_type", "created_at"],
    )
    # Tenant-only counts/filters.
    op.create_index(
        "idx_asset_lib_tenant_id",
        "asset_libraries",
        ["tenant_id"],
    )
    # Category filter for the "browse by category" view.
    op.create_index(
        "idx_asset_lib_category",
        "asset_libraries",
        ["category"],
    )


def downgrade():
    op.drop_index("idx_asset_lib_category", table_name="asset_libraries")
    op.drop_index("idx_asset_lib_tenant_id", table_name="asset_libraries")
    op.drop_index("idx_asset_lib_tenant_type_created", table_name="asset_libraries")
    op.drop_table("asset_libraries")
