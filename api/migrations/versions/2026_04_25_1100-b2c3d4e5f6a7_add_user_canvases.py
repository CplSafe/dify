"""add user_canvases table for canvas-runtime saved snapshots

Each row is a user's named pointer to a successful workflow_run; the
snapshot data itself (nodes, inputs/outputs) lives in workflow_run +
workflow_node_executions and is re-derived on open.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-25 11:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_canvases",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("app_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        # source_run_id points at workflow_runs.id; we don't FK because
        # workflow runs can be GC'd and we want the row to stay around so
        # the user sees a "snapshot expired" placeholder instead of a 404.
        sa.Column("source_run_id", sa.String(36), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="user_canvas_pkey"),
    )
    # Owner-scoped list query, newest first.
    op.create_index(
        "user_canvas_owner_created_idx",
        "user_canvases",
        ["owner_id", sa.text("created_at DESC")],
    )
    # Tenant + app filter for "all canvases under this app" admin views.
    op.create_index(
        "user_canvas_tenant_app_idx",
        "user_canvases",
        ["tenant_id", "app_id"],
    )


def downgrade():
    op.drop_index("user_canvas_tenant_app_idx", table_name="user_canvases")
    op.drop_index("user_canvas_owner_created_idx", table_name="user_canvases")
    op.drop_table("user_canvases")
