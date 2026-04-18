"""add social_publish_tasks table

Revision ID: f990c4cbf08a
Revises: 57f95942bc8a
Create Date: 2026-04-18 11:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f990c4cbf08a"
down_revision = "57f95942bc8a"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    """Whether the bound migration context is targeting Postgres.

    The production target IS Postgres; this guard exists so SQLite-backed
    test setups (and any future devs running alembic against a non-PG dev
    db) don't choke on the JSONB column type or the partial index.
    """
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade():
    payload_type: sa.types.TypeEngine
    if _is_postgres():
        payload_type = postgresql.JSONB(astext_type=sa.Text())
    else:
        payload_type = sa.JSON()
    op.create_table(
        "social_publish_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("work_id", sa.String(36), nullable=True),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("sau_task_id", sa.String(64), nullable=True),
        sa.Column(
            "payload",
            payload_type,
            nullable=False,
        ),
        sa.Column("result_url", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="social_publish_task_pkey"),
    )
    op.create_index(
        "social_publish_task_tenant_created_idx",
        "social_publish_tasks",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "social_publish_task_account_idx",
        "social_publish_tasks",
        ["account_id"],
    )
    op.create_index(
        "social_publish_task_status_idx",
        "social_publish_tasks",
        ["status"],
    )
    if _is_postgres():
        # Partial indexes are Postgres-only; skip the WHERE predicate on
        # other dialects so SQLite test runs don't choke. The full index
        # below is wider than the partial one but functionally equivalent
        # for the lookup-by-sau_task_id path.
        op.create_index(
            "social_publish_task_sau_task_idx",
            "social_publish_tasks",
            ["sau_task_id"],
            postgresql_where=sa.text("sau_task_id IS NOT NULL"),
        )
    else:
        op.create_index(
            "social_publish_task_sau_task_idx",
            "social_publish_tasks",
            ["sau_task_id"],
        )


def downgrade():
    op.drop_index("social_publish_task_sau_task_idx", table_name="social_publish_tasks")
    op.drop_index("social_publish_task_status_idx", table_name="social_publish_tasks")
    op.drop_index("social_publish_task_account_idx", table_name="social_publish_tasks")
    op.drop_index("social_publish_task_tenant_created_idx", table_name="social_publish_tasks")
    op.drop_table("social_publish_tasks")
