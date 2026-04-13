"""add creator_tasks table

Revision ID: a3f7c2d1e8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-04-13 15:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = 'a3f7c2d1e8b9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def _uuid_col(name, nullable=False, **kwargs):
    """Return a UUID column for PostgreSQL, VARCHAR(36) for other DBs."""
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        return sa.Column(name, UUID(), nullable=nullable, **kwargs)
    return sa.Column(name, sa.String(36), nullable=nullable, **kwargs)


def upgrade():
    conn = op.get_bind()
    is_pg = conn.dialect.name == 'postgresql'

    # Table may already exist if migration was partially applied
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='creator_tasks'"
        )
    )
    if result.fetchone() is not None:
        return

    if is_pg:
        op.create_table(
            'creator_tasks',
            sa.Column('id', UUID(), nullable=False),
            sa.Column('account_id', UUID(), nullable=False),
            sa.Column('tenant_id', UUID(), nullable=False),
            sa.Column('app_id', UUID(), nullable=False),
            sa.Column('installed_app_id', UUID(), nullable=False),
            sa.Column('conversation_id', UUID(), nullable=True),
            sa.Column('workflow_run_id', UUID(), nullable=True),
            sa.Column('status', sa.String(20), server_default='running', nullable=False),
            sa.Column('title', sa.String(200), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id', name='creator_task_pkey'),
        )
    else:
        op.create_table(
            'creator_tasks',
            sa.Column('id', sa.String(36), nullable=False),
            sa.Column('account_id', sa.String(36), nullable=False),
            sa.Column('tenant_id', sa.String(36), nullable=False),
            sa.Column('app_id', sa.String(36), nullable=False),
            sa.Column('installed_app_id', sa.String(36), nullable=False),
            sa.Column('conversation_id', sa.String(36), nullable=True),
            sa.Column('workflow_run_id', sa.String(36), nullable=True),
            sa.Column('status', sa.String(20), server_default='running', nullable=False),
            sa.Column('title', sa.String(200), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='creator_task_pkey'),
        )

    op.create_index(
        'idx_creator_tasks_user_status',
        'creator_tasks',
        ['account_id', 'status', 'created_at'],
    )
    op.create_index(
        'idx_creator_tasks_conversation',
        'creator_tasks',
        ['conversation_id'],
    )


def downgrade():
    op.drop_index('idx_creator_tasks_conversation', table_name='creator_tasks')
    op.drop_index('idx_creator_tasks_user_status', table_name='creator_tasks')
    op.drop_table('creator_tasks')
