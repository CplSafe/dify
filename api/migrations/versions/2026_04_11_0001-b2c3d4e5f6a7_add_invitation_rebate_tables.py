"""add invitation and rebate tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-11 00:01:00.000000

"""
import sqlalchemy as sa
from alembic import op

import models as models

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _is_pg(conn):
    return conn.dialect.name == "postgresql"


def upgrade():
    conn = op.get_bind()
    is_pg = _is_pg(conn)

    # 1. account_invitations
    if is_pg:
        op.create_table(
            'account_invitations',
            sa.Column('id', models.types.StringUUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('invite_code', sa.String(length=64), nullable=False),
            sa.Column('inviter_account_id', models.types.StringUUID(), nullable=False),
            sa.Column('invitee_account_id', models.types.StringUUID(), nullable=True),
            sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id', name='account_invitation_pkey'),
        )
    else:
        op.create_table(
            'account_invitations',
            sa.Column('id', models.types.StringUUID(), nullable=False),
            sa.Column('invite_code', sa.String(length=64), nullable=False),
            sa.Column('inviter_account_id', models.types.StringUUID(), nullable=False),
            sa.Column('invitee_account_id', models.types.StringUUID(), nullable=True),
            sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column('used_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id', name='account_invitation_pkey'),
        )
    with op.batch_alter_table('account_invitations', schema=None) as batch_op:
        batch_op.create_index('account_invitation_code_idx', ['invite_code'], unique=True)
        batch_op.create_index('account_invitation_inviter_idx', ['inviter_account_id'], unique=False)
        batch_op.create_index('account_invitation_invitee_idx', ['invitee_account_id'], unique=False)

    # 2. rebate_configs
    if is_pg:
        op.create_table(
            'rebate_configs',
            sa.Column('id', models.types.StringUUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('rebate_rate', sa.Numeric(precision=10, scale=4), server_default='10', nullable=False),
            sa.Column('cost_rate', sa.Numeric(precision=10, scale=4), server_default='0', nullable=False),
            sa.Column('settlement_hour', sa.Integer(), server_default='2', nullable=False),
            sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
            sa.Column('updated_by', models.types.StringUUID(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id', name='rebate_config_pkey'),
        )
    else:
        op.create_table(
            'rebate_configs',
            sa.Column('id', models.types.StringUUID(), nullable=False),
            sa.Column('rebate_rate', sa.Numeric(precision=10, scale=4), server_default='10', nullable=False),
            sa.Column('cost_rate', sa.Numeric(precision=10, scale=4), server_default='0', nullable=False),
            sa.Column('settlement_hour', sa.Integer(), server_default='2', nullable=False),
            sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('1'), nullable=False),
            sa.Column('updated_by', models.types.StringUUID(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='rebate_config_pkey'),
        )

    # 3. rebate_records
    if is_pg:
        op.create_table(
            'rebate_records',
            sa.Column('id', models.types.StringUUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
            sa.Column('inviter_account_id', models.types.StringUUID(), nullable=False),
            sa.Column('invitee_account_id', models.types.StringUUID(), nullable=False),
            sa.Column('settlement_date', sa.String(length=10), nullable=False),
            sa.Column('consumption_amount', sa.Numeric(precision=20, scale=6), nullable=False),
            sa.Column('cost_amount', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False),
            sa.Column('rebate_amount', sa.Numeric(precision=20, scale=6), nullable=False),
            sa.Column('rebate_rate', sa.Numeric(precision=10, scale=4), nullable=False),
            sa.Column('cost_rate', sa.Numeric(precision=10, scale=4), server_default='0', nullable=False),
            sa.Column('currency', sa.String(length=10), server_default='CNY', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('id', name='rebate_record_pkey'),
        )
    else:
        op.create_table(
            'rebate_records',
            sa.Column('id', models.types.StringUUID(), nullable=False),
            sa.Column('inviter_account_id', models.types.StringUUID(), nullable=False),
            sa.Column('invitee_account_id', models.types.StringUUID(), nullable=False),
            sa.Column('settlement_date', sa.String(length=10), nullable=False),
            sa.Column('consumption_amount', sa.Numeric(precision=20, scale=6), nullable=False),
            sa.Column('cost_amount', sa.Numeric(precision=20, scale=6), server_default='0', nullable=False),
            sa.Column('rebate_amount', sa.Numeric(precision=20, scale=6), nullable=False),
            sa.Column('rebate_rate', sa.Numeric(precision=10, scale=4), nullable=False),
            sa.Column('cost_rate', sa.Numeric(precision=10, scale=4), server_default='0', nullable=False),
            sa.Column('currency', sa.String(length=10), server_default='CNY', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='rebate_record_pkey'),
        )
    with op.batch_alter_table('rebate_records', schema=None) as batch_op:
        batch_op.create_index('rebate_record_inviter_idx', ['inviter_account_id'], unique=False)
        batch_op.create_index('rebate_record_invitee_idx', ['invitee_account_id'], unique=False)
        batch_op.create_index('rebate_record_date_idx', ['settlement_date'], unique=False)
        batch_op.create_index('rebate_record_inviter_date_idx', ['inviter_account_id', 'settlement_date'], unique=False)


def downgrade():
    with op.batch_alter_table('rebate_records', schema=None) as batch_op:
        batch_op.drop_index('rebate_record_inviter_date_idx')
        batch_op.drop_index('rebate_record_date_idx')
        batch_op.drop_index('rebate_record_invitee_idx')
        batch_op.drop_index('rebate_record_inviter_idx')
    op.drop_table('rebate_records')

    op.drop_table('rebate_configs')

    with op.batch_alter_table('account_invitations', schema=None) as batch_op:
        batch_op.drop_index('account_invitation_invitee_idx')
        batch_op.drop_index('account_invitation_inviter_idx')
        batch_op.drop_index('account_invitation_code_idx')
    op.drop_table('account_invitations')
