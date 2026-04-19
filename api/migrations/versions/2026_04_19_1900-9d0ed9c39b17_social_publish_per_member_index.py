"""add (tenant_id, created_by, platform) composite index

Revision ID: 9d0ed9c39b17
Revises: a918a826301d
Create Date: 2026-04-19 19:00:00.000000

P8 introduces per-member account isolation: ``list_by_tenant_and_user``
filters on ``WHERE tenant_id = ? AND created_by = ?`` (optionally also
``platform = ?``). The existing ``(tenant_id, platform)`` index doesn't
cover ``created_by`` directly, so the planner has to scan the per-tenant
slice on every member-scoped list query. This composite covers all
three filter columns in the order they're applied.

Pure DDL: no data backfill needed because ``created_by`` has been
populated since P1 — every existing row already has the right value.

"""

from alembic import op

revision = "9d0ed9c39b17"
down_revision = "a918a826301d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "social_publish_account_tenant_user_platform_idx",
        "social_publish_accounts",
        ["tenant_id", "created_by", "platform"],
    )


def downgrade():
    op.drop_index(
        "social_publish_account_tenant_user_platform_idx",
        table_name="social_publish_accounts",
    )
