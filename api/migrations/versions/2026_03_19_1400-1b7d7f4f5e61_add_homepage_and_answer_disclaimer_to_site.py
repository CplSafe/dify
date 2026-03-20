"""add homepage and answer disclaimer toggles to site

Revision ID: 1b7d7f4f5e61
Revises: 0ec65df55790
Create Date: 2026-03-19 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1b7d7f4f5e61"
down_revision = "0ec65df55790"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("sites", schema=None) as batch_op:
        batch_op.add_column(sa.Column("enable_homepage", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch_op.add_column(
            sa.Column("show_answer_disclaimer", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )


def downgrade():
    with op.batch_alter_table("sites", schema=None) as batch_op:
        batch_op.drop_column("show_answer_disclaimer")
        batch_op.drop_column("enable_homepage")
