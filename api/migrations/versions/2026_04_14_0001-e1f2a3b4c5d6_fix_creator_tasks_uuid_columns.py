"""fix creator_tasks uuid columns from varchar to uuid

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-04-14 00:01:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None

UUID_COLUMNS = [
    'id',
    'account_id',
    'tenant_id',
    'app_id',
    'installed_app_id',
    'conversation_id',
    'workflow_run_id',
]


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    # Check whether the columns are already uuid type; skip if so.
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'creator_tasks' "
            "AND data_type = 'character varying' "
            "AND column_name = ANY(:cols)"
        ),
        {'cols': UUID_COLUMNS},
    )
    varchar_cols = [row[0] for row in result]
    if not varchar_cols:
        return

    for col in varchar_cols:
        op.execute(
            sa.text(
                f'ALTER TABLE creator_tasks '
                f'ALTER COLUMN {col} TYPE uuid USING {col}::uuid'
            )
        )


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    for col in UUID_COLUMNS:
        op.execute(
            sa.text(
                f'ALTER TABLE creator_tasks '
                f'ALTER COLUMN {col} TYPE character varying(36) USING {col}::text'
            )
        )
