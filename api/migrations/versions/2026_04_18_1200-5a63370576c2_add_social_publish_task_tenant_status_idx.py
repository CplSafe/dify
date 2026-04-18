"""add (tenant_id, status) composite index on social_publish_tasks

Revision ID: 5a63370576c2
Revises: f990c4cbf08a
Create Date: 2026-04-18 12:00:00.000000

P3 introduces a per-tenant quota check (``count_active_for_tenant``)
that filters on both columns. The existing ``(tenant_id, created_at)``
and ``(status)`` indexes don't cover that combination directly, so the
planner has to scan the per-tenant slice on every quota dispatch.

"""

from alembic import op

revision = "5a63370576c2"
down_revision = "f990c4cbf08a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "social_publish_task_tenant_status_idx",
        "social_publish_tasks",
        ["tenant_id", "status"],
    )


def downgrade():
    op.drop_index(
        "social_publish_task_tenant_status_idx",
        table_name="social_publish_tasks",
    )
