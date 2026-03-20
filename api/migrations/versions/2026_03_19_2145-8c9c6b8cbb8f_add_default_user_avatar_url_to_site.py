"""add default user avatar url to site

Revision ID: 8c9c6b8cbb8f
Revises: 1b7d7f4f5e61
Create Date: 2026-03-19 21:45:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8c9c6b8cbb8f"
down_revision = "eb865466e489"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sites", sa.Column("default_user_avatar_url", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("sites", "default_user_avatar_url")
