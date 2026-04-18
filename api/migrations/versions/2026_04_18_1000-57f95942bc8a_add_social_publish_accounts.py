"""add social_publish_accounts table

Revision ID: 57f95942bc8a
Revises: cbc30aed1134
Create Date: 2026-04-18 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "57f95942bc8a"
down_revision = "cbc30aed1134"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "social_publish_accounts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("sau_account_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending_auth",
        ),
        sa.Column("last_check_at", sa.DateTime(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="social_publish_account_pkey"),
    )
    op.create_index(
        "social_publish_account_tenant_platform_idx",
        "social_publish_accounts",
        ["tenant_id", "platform"],
    )
    op.create_index(
        "social_publish_account_sau_account_id_uk",
        "social_publish_accounts",
        ["sau_account_id"],
        unique=True,
    )
    op.create_index(
        "social_publish_account_status_idx",
        "social_publish_accounts",
        ["status"],
    )


def downgrade():
    op.drop_index(
        "social_publish_account_status_idx",
        table_name="social_publish_accounts",
    )
    op.drop_index(
        "social_publish_account_sau_account_id_uk",
        table_name="social_publish_accounts",
    )
    op.drop_index(
        "social_publish_account_tenant_platform_idx",
        table_name="social_publish_accounts",
    )
    op.drop_table("social_publish_accounts")
