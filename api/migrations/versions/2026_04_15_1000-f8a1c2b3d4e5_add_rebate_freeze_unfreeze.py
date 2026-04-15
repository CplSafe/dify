"""add rebate freeze/unfreeze support

Revision ID: f8a1c2b3d4e5
Revises: ceb6041f35cf
Create Date: 2026-04-15 10:00:00.000000

Adds the data needed to hold rebate income in escrow for a configurable
window before it becomes spendable:

- ``user_balances.rebate_pending``: frozen rebate, not spendable yet.
- ``rebate_configs.freeze_days``: how long rebates sit pending (default 7).
- ``rebate_records.status``: pending | settled | cancelled.
- ``rebate_records.unfrozen_at``: timestamp of the settled/cancelled
  transition. NULL for still-pending rows.

Historical rows (pre-freeze deployment) are backfilled to ``settled`` with
``unfrozen_at = created_at`` so the new scan (`status='pending' AND
created_at <= cutoff`) doesn't sweep them up and double-credit their
rebates.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8a1c2b3d4e5'
down_revision = 'ceb6041f35cf'
branch_labels = None
depends_on = None


def upgrade():
    # UserBalance: add rebate_pending bucket.
    with op.batch_alter_table('user_balances', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'rebate_pending',
                sa.Numeric(precision=20, scale=6),
                server_default='0',
                nullable=False,
            )
        )

    # RebateConfig: add freeze_days.
    with op.batch_alter_table('rebate_configs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('freeze_days', sa.Integer(), server_default='7', nullable=False)
        )

    # RebateRecord: add status + unfrozen_at + supporting index.
    # Default server-side to 'settled' so backfill of existing rows treats
    # them as fully released — they were already credited to UserBalance.balance
    # under the legacy (no-freeze) flow, and the unfreeze task must NOT
    # re-credit them.
    with op.batch_alter_table('rebate_records', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'status',
                sa.String(length=20),
                server_default='settled',
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column('unfrozen_at', sa.DateTime(), nullable=True))

    # Backfill: mark existing rebate records as already settled/released,
    # pointing unfrozen_at at their created_at so the operational view
    # reflects "this was credited on day X" rather than leaving a NULL that
    # could look like a stuck row.
    op.execute(
        "UPDATE rebate_records "
        "SET unfrozen_at = created_at "
        "WHERE status = 'settled' AND unfrozen_at IS NULL"
    )

    # Flip the server default to 'pending' going forward — new rows created
    # by the settlement task are frozen first, then released by the unfreeze
    # task. Existing rows keep their backfilled 'settled' value.
    with op.batch_alter_table('rebate_records', schema=None) as batch_op:
        batch_op.alter_column(
            'status',
            server_default='pending',
            existing_type=sa.String(length=20),
            existing_nullable=False,
        )
        batch_op.create_index(
            'rebate_record_status_created_idx',
            ['status', 'created_at'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('rebate_records', schema=None) as batch_op:
        batch_op.drop_index('rebate_record_status_created_idx')
        batch_op.drop_column('unfrozen_at')
        batch_op.drop_column('status')

    with op.batch_alter_table('rebate_configs', schema=None) as batch_op:
        batch_op.drop_column('freeze_days')

    with op.batch_alter_table('user_balances', schema=None) as batch_op:
        batch_op.drop_column('rebate_pending')
