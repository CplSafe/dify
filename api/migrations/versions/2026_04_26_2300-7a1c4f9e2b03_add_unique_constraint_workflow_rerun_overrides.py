"""add unique constraint on workflow_rerun_overrides (message_id, node_id, override_kind)

CR10 review fix: the original `workflow_rerun_overrides` table relied on
the service-layer "select then insert/update" upsert in
`WorkflowRerunService.upsert_override`. Two concurrent saves on the same
(message, node, kind) tuple race past the SELECT and produce duplicate
rows; subsequent reads then return whichever the planner picks first,
which is non-deterministic.

This migration adds a real DB-level uniqueness guarantee so the upsert
path can switch to an atomic Postgres INSERT ... ON CONFLICT.

Revision ID: 7a1c4f9e2b03
Revises: 38ce6eaa16f7
Create Date: 2026-04-26 23:00:00.000000

"""

from alembic import op

revision = "7a1c4f9e2b03"
down_revision = "38ce6eaa16f7"
branch_labels = None
depends_on = None


_INDEX_NAME = "workflow_rerun_override_message_node_kind_uq"


def upgrade():
    # Drop any duplicate rows that might exist from pre-constraint inserts,
    # keeping the most recently created row per (message_id, node_id, kind)
    # tuple. Without this the constraint creation would fail on dirty data.
    op.execute(
        """
        DELETE FROM workflow_rerun_overrides a
        USING workflow_rerun_overrides b
        WHERE a.id != b.id
          AND a.message_id = b.message_id
          AND a.node_id = b.node_id
          AND a.override_kind = b.override_kind
          AND a.created_at < b.created_at
        """
    )
    op.create_index(
        _INDEX_NAME,
        "workflow_rerun_overrides",
        ["message_id", "node_id", "override_kind"],
        unique=True,
    )


def downgrade():
    op.drop_index(_INDEX_NAME, table_name="workflow_rerun_overrides")
