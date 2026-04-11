"""add creator platform tables

Revision ID: a1b2c3d4e5f6
Revises: 7df29de0f6be
Create Date: 2026-04-10 00:01:00.000000

"""
import sqlalchemy as sa
from alembic import op

import models as models

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'c3e9b6a2d1f4'
branch_labels = None
depends_on = None


def _is_pg(conn):
    return conn.dialect.name == "postgresql"


def upgrade():
    conn = op.get_bind()
    is_pg = _is_pg(conn)

    # 1. Add is_system_admin to accounts table
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_system_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    # 2. Create user_balances table
    if is_pg:
        op.create_table(
            'user_balances',
            sa.Column('id', models.types.StringUUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('account_id', models.types.StringUUID(), nullable=False),
            sa.Column('balance', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False),
            sa.Column('currency', sa.String(length=10), server_default='CNY', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id', name='user_balance_pkey'),
        )
    else:
        op.create_table(
            'user_balances',
            sa.Column('id', models.types.StringUUID(), nullable=False),
            sa.Column('account_id', models.types.StringUUID(), nullable=False),
            sa.Column('balance', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False),
            sa.Column('currency', sa.String(length=10), server_default='CNY', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='user_balance_pkey'),
        )
    with op.batch_alter_table('user_balances', schema=None) as batch_op:
        batch_op.create_index('user_balance_account_id_idx', ['account_id'], unique=True)

    # 3. Create billing_records table
    if is_pg:
        op.create_table(
            'billing_records',
            sa.Column('id', models.types.StringUUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('account_id', models.types.StringUUID(), nullable=False),
            sa.Column('tenant_id', models.types.StringUUID(), nullable=True),
            sa.Column('workflow_run_id', models.types.StringUUID(), nullable=True),
            sa.Column('amount', sa.Numeric(precision=20, scale=6), nullable=False),
            sa.Column('currency', sa.String(length=10), server_default='CNY', nullable=False),
            sa.Column('record_type', sa.String(length=20), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id', name='billing_record_pkey'),
        )
    else:
        op.create_table(
            'billing_records',
            sa.Column('id', models.types.StringUUID(), nullable=False),
            sa.Column('account_id', models.types.StringUUID(), nullable=False),
            sa.Column('tenant_id', models.types.StringUUID(), nullable=True),
            sa.Column('workflow_run_id', models.types.StringUUID(), nullable=True),
            sa.Column('amount', sa.Numeric(precision=20, scale=6), nullable=False),
            sa.Column('currency', sa.String(length=10), server_default='CNY', nullable=False),
            sa.Column('record_type', sa.String(length=20), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='billing_record_pkey'),
        )
    with op.batch_alter_table('billing_records', schema=None) as batch_op:
        batch_op.create_index('billing_record_account_id_idx', ['account_id'], unique=False)
        batch_op.create_index('billing_record_tenant_id_idx', ['tenant_id'], unique=False)
        batch_op.create_index('billing_record_account_created_idx', ['account_id', 'created_at'], unique=False)

    # 4. Create marketplace_apps table
    if is_pg:
        op.create_table(
            'marketplace_apps',
            sa.Column('id', models.types.StringUUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('app_id', models.types.StringUUID(), nullable=False),
            sa.Column('published_by', models.types.StringUUID(), nullable=False),
            sa.Column('published_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
            sa.PrimaryKeyConstraint('id', name='marketplace_app_pkey'),
        )
    else:
        op.create_table(
            'marketplace_apps',
            sa.Column('id', models.types.StringUUID(), nullable=False),
            sa.Column('app_id', models.types.StringUUID(), nullable=False),
            sa.Column('published_by', models.types.StringUUID(), nullable=False),
            sa.Column('published_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
            sa.PrimaryKeyConstraint('id', name='marketplace_app_pkey'),
        )
    with op.batch_alter_table('marketplace_apps', schema=None) as batch_op:
        batch_op.create_index('marketplace_app_app_id_idx', ['app_id'], unique=True)
        batch_op.create_index('marketplace_app_published_at_idx', ['published_at'], unique=False)

    # 5. Create user_global_api_keys table
    if is_pg:
        op.create_table(
            'user_global_api_keys',
            sa.Column('id', models.types.StringUUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('account_id', models.types.StringUUID(), nullable=False),
            sa.Column('token', sa.String(length=255), nullable=False),
            sa.Column('description', sa.String(length=255), nullable=True),
            sa.Column('last_used_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id', name='user_global_api_key_pkey'),
        )
    else:
        op.create_table(
            'user_global_api_keys',
            sa.Column('id', models.types.StringUUID(), nullable=False),
            sa.Column('account_id', models.types.StringUUID(), nullable=False),
            sa.Column('token', sa.String(length=255), nullable=False),
            sa.Column('description', sa.String(length=255), nullable=True),
            sa.Column('last_used_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='user_global_api_key_pkey'),
        )
    with op.batch_alter_table('user_global_api_keys', schema=None) as batch_op:
        batch_op.create_index('user_global_api_key_account_id_idx', ['account_id'], unique=True)
        batch_op.create_index('user_global_api_key_token_idx', ['token'], unique=True)

    # 6. Create creator_works table
    if is_pg:
        op.create_table(
            'creator_works',
            sa.Column('id', models.types.StringUUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('account_id', models.types.StringUUID(), nullable=False),
            sa.Column('tenant_id', models.types.StringUUID(), nullable=False),
            sa.Column('workflow_run_id', models.types.StringUUID(), nullable=True),
            sa.Column('app_id', models.types.StringUUID(), nullable=True),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('file_key', sa.String(length=500), nullable=True),
            sa.Column('file_type', sa.String(length=50), server_default='video', nullable=False),
            sa.Column('share_status', sa.String(length=50), server_default='draft', nullable=False),
            sa.Column('output_data', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id', name='creator_work_pkey'),
        )
    else:
        op.create_table(
            'creator_works',
            sa.Column('id', models.types.StringUUID(), nullable=False),
            sa.Column('account_id', models.types.StringUUID(), nullable=False),
            sa.Column('tenant_id', models.types.StringUUID(), nullable=False),
            sa.Column('workflow_run_id', models.types.StringUUID(), nullable=True),
            sa.Column('app_id', models.types.StringUUID(), nullable=True),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('file_key', sa.String(length=500), nullable=True),
            sa.Column('file_type', sa.String(length=50), server_default='video', nullable=False),
            sa.Column('share_status', sa.String(length=50), server_default='draft', nullable=False),
            sa.Column('output_data', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='creator_work_pkey'),
        )
    with op.batch_alter_table('creator_works', schema=None) as batch_op:
        batch_op.create_index('creator_work_account_id_idx', ['account_id'], unique=False)
        batch_op.create_index('creator_work_tenant_id_idx', ['tenant_id'], unique=False)
        batch_op.create_index('creator_work_created_at_idx', ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('creator_works', schema=None) as batch_op:
        batch_op.drop_index('creator_work_created_at_idx')
        batch_op.drop_index('creator_work_tenant_id_idx')
        batch_op.drop_index('creator_work_account_id_idx')
    op.drop_table('creator_works')

    with op.batch_alter_table('user_global_api_keys', schema=None) as batch_op:
        batch_op.drop_index('user_global_api_key_token_idx')
        batch_op.drop_index('user_global_api_key_account_id_idx')
    op.drop_table('user_global_api_keys')

    with op.batch_alter_table('marketplace_apps', schema=None) as batch_op:
        batch_op.drop_index('marketplace_app_published_at_idx')
        batch_op.drop_index('marketplace_app_app_id_idx')
    op.drop_table('marketplace_apps')

    with op.batch_alter_table('billing_records', schema=None) as batch_op:
        batch_op.drop_index('billing_record_account_created_idx')
        batch_op.drop_index('billing_record_tenant_id_idx')
        batch_op.drop_index('billing_record_account_id_idx')
    op.drop_table('billing_records')

    with op.batch_alter_table('user_balances', schema=None) as batch_op:
        batch_op.drop_index('user_balance_account_id_idx')
    op.drop_table('user_balances')

    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_column('is_system_admin')
