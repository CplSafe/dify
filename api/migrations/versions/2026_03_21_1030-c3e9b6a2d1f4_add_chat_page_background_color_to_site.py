"""add chat page background color to site

Revision ID: c3e9b6a2d1f4
Revises: 8c9c6b8cbb8f
Create Date: 2026-03-21 10:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c3e9b6a2d1f4"
down_revision = "8c9c6b8cbb8f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sites", sa.Column("chat_page_background_color", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("sites", "chat_page_background_color")
