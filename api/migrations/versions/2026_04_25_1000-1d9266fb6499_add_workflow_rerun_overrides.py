"""add workflow_rerun_overrides table for chatflow node-level rerun

Stores per-message overrides of node inputs/outputs so users can edit
intermediate results and re-run downstream nodes without losing the
original execution data.

Revision ID: 1d9266fb6499
Revises: 9d0ed9c39b17
Create Date: 2026-04-25 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

import models.types

revision = "1d9266fb6499"
down_revision = "9d0ed9c39b17"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workflow_rerun_overrides",
        # Use StringUUID so PostgreSQL stores these as native uuid columns
        # and joins to message / workflow_run id columns don't fail with
        # `varchar = uuid` operator errors at query time.
        sa.Column("id", models.types.StringUUID(), nullable=False),
        sa.Column("message_id", models.types.StringUUID(), nullable=False),
        sa.Column("workflow_run_id", models.types.StringUUID(), nullable=False),
        sa.Column("node_id", sa.String(255), nullable=False),
        # 'input' overrides what the node receives (rerun starts at this node).
        # 'output' overrides what the node produces (rerun starts at the
        # downstream node, this node itself is skipped and replaced).
        sa.Column("override_kind", sa.String(16), nullable=False),
        sa.Column("override_data", sa.JSON(), nullable=False),
        sa.Column("created_by", models.types.StringUUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="workflow_rerun_override_pkey"),
    )
    op.create_index(
        "workflow_rerun_override_message_node_idx",
        "workflow_rerun_overrides",
        ["message_id", "node_id"],
    )
    op.create_index(
        "workflow_rerun_override_run_idx",
        "workflow_rerun_overrides",
        ["workflow_run_id"],
    )


def downgrade():
    op.drop_index(
        "workflow_rerun_override_run_idx",
        table_name="workflow_rerun_overrides",
    )
    op.drop_index(
        "workflow_rerun_override_message_node_idx",
        table_name="workflow_rerun_overrides",
    )
    op.drop_table("workflow_rerun_overrides")
