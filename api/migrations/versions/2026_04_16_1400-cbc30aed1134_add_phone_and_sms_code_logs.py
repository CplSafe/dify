"""add phone column to accounts and sms_code_logs table

Revision ID: cbc30aed1134
Revises: c3e9b6a2d1f4
Create Date: 2026-04-16 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "cbc30aed1134"
down_revision = "f8a1c2b3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    # Add phone column to accounts table
    op.add_column("accounts", sa.Column("phone", sa.String(20), nullable=True))
    op.create_unique_constraint("uq_accounts_phone", "accounts", ["phone"])
    op.create_index("account_phone_idx", "accounts", ["phone"])

    # Create sms_code_logs table
    op.create_table(
        "sms_code_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("sent_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="sms_code_log_pkey"),
    )
    op.create_index("sms_code_log_phone_idx", "sms_code_logs", ["phone"])
    op.create_index("sms_code_log_sent_at_idx", "sms_code_logs", ["sent_at"])


def downgrade():
    op.drop_index("sms_code_log_sent_at_idx", table_name="sms_code_logs")
    op.drop_index("sms_code_log_phone_idx", table_name="sms_code_logs")
    op.drop_table("sms_code_logs")
    op.drop_index("account_phone_idx", table_name="accounts")
    op.drop_constraint("uq_accounts_phone", "accounts", type_="unique")
    op.drop_column("accounts", "phone")
