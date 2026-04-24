"""add workflow_rerun_overrides table for chatflow node-level rerun

Stores per-message overrides of node inputs/outputs so users can edit
intermediate results and re-run downstream nodes without losing the
original execution data.

Revision ID: a1b2c3d4e5f6
Revises: 9d0ed9c39b17
Create Date: 2026-04-25 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "9d0ed9c39b17"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workflow_rerun_overrides",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("message_id", sa.String(36), nullable=False),
        sa.Column("workflow_run_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(255), nullable=False),
        # 'input' overrides what the node receives (rerun starts at this node).
        # 'output' overrides what the node produces (rerun starts at the
        # downstream node, this node itself is skipped and replaced).
        sa.Column("override_kind", sa.String(16), nullable=False),
        sa.Column("override_data", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
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
