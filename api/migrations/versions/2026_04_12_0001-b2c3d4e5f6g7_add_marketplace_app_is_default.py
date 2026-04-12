"""add is_default to marketplace_apps

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-12 00:01:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'marketplace_apps',
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )


def downgrade():
    op.drop_column('marketplace_apps', 'is_default')
