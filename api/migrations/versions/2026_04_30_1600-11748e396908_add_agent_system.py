"""add agent system

Phase 0 of the agent-system rollout. Creates four new tables and rewires
the legacy invitation/rebate ledger so that only authorized agents can
earn referral rebates.

New tables:

- ``agents`` — one row per authorized agent account, opened by sysadmin.
- ``agent_wallets`` — 1:1 with ``agents``; tracks withdrawable balance,
  total earned, total withdrawn. CHECK constraint pins ``withdrawable >= 0``.
- ``rebind_requests`` — customer-initiated rebind workflow rows.
  Partial unique index enforces "at most one pending request per account".
- ``withdrawal_requests`` — agent-initiated payout requests.
  Partial unique index enforces "at most one pending request per agent".

Modified tables:

- ``account_invitations`` — adds NOT NULL ``agent_id`` (FK by convention,
  no DB-level FK per Dify). Drops the unique constraint on ``invite_code``
  so a single code can have multiple invitee rows (codes are reusable).
- ``rebate_records`` — adds NOT NULL ``agent_id`` so historic earnings
  stay locked to the original agent across rebinds.
- ``user_balances`` — drops ``rebate_pending`` (moved to ``agent_wallets``).

Historic data wipe (per design §6.1): both ``account_invitations`` and
``rebate_records`` are TRUNCATEd because the old "any user can refer"
semantics is dead. Rolling back this migration cannot recover the wiped
rows; production rollbacks must back up first.

Revision ID: 11748e396908
Revises: ba0600085c24
Create Date: 2026-04-30 16:00:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "11748e396908"
down_revision = "ba0600085c24"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create agents table
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("rebate_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=True),
        sa.Column("region_province", sa.String(length=32), nullable=True),
        sa.Column("region_city", sa.String(length=32), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("signed_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="agent_pkey"),
    )
    op.create_index("agent_account_id_idx", "agents", ["account_id"], unique=True)
    op.create_index("agent_status_idx", "agents", ["status"])
    op.create_index("agent_expires_at_idx", "agents", ["expires_at"])

    # 2. Create agent_wallets table
    op.create_table(
        "agent_wallets",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("withdrawable", sa.Numeric(precision=20, scale=6), server_default="0", nullable=False),
        sa.Column("total_earned", sa.Numeric(precision=20, scale=6), server_default="0", nullable=False),
        sa.Column("total_withdrawn", sa.Numeric(precision=20, scale=6), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="agent_wallet_pkey"),
        sa.CheckConstraint("withdrawable >= 0", name="agent_wallet_withdrawable_nonneg"),
    )
    op.create_index("agent_wallet_agent_id_idx", "agent_wallets", ["agent_id"], unique=True)

    # 3. Create rebind_requests table
    op.create_table(
        "rebind_requests",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("from_agent_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("to_agent_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="rebind_request_pkey"),
    )
    op.create_index("rebind_request_account_id_idx", "rebind_requests", ["account_id"])
    op.create_index(
        "rebind_request_pending_unique_idx",
        "rebind_requests",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # 4. Create withdrawal_requests table
    op.create_table(
        "withdrawal_requests",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("payout_method", sa.String(length=16), nullable=False),
        sa.Column("payout_payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="withdrawal_request_pkey"),
    )
    op.create_index("withdrawal_request_agent_id_idx", "withdrawal_requests", ["agent_id"])
    op.create_index(
        "withdrawal_request_pending_unique_idx",
        "withdrawal_requests",
        ["agent_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # 5. Add agent_id columns to existing tables (nullable while data is wiped)
    op.add_column(
        "account_invitations",
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.add_column(
        "rebate_records",
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_index("account_invitation_agent_idx", "account_invitations", ["agent_id"])
    op.create_index("rebate_record_agent_idx", "rebate_records", ["agent_id"])

    # 6. Wipe historic invitation/rebate data (per design §6.1).
    #    The old "any user can refer" semantic is dead — these rows
    #    cannot satisfy the new NOT NULL agent_id constraint, and there
    #    is no agent to migrate them to.
    op.execute("TRUNCATE rebate_records CASCADE")
    op.execute("TRUNCATE account_invitations CASCADE")

    # 7. Now make agent_id NOT NULL on both tables.
    op.alter_column("account_invitations", "agent_id", nullable=False)
    op.alter_column("rebate_records", "agent_id", nullable=False)

    # 8. Drop the old unique constraint on account_invitations.invite_code.
    #    Code is reusable now — same code, multiple invitee rows.
    op.drop_index("account_invitation_code_idx", table_name="account_invitations")
    op.create_index("account_invitation_code_idx", "account_invitations", ["invite_code"])

    # 9. Drop rebate_pending from user_balances (replaced by agent_wallets.withdrawable).
    op.drop_column("user_balances", "rebate_pending")


def downgrade():
    # Reverse order. NOTE: TRUNCATE'd data is NOT recoverable — production
    # rollbacks must back up before running this downgrade.
    op.add_column(
        "user_balances",
        sa.Column(
            "rebate_pending",
            sa.Numeric(precision=20, scale=6),
            server_default="0",
            nullable=False,
        ),
    )
    op.drop_index("account_invitation_code_idx", table_name="account_invitations")
    op.create_index(
        "account_invitation_code_idx",
        "account_invitations",
        ["invite_code"],
        unique=True,
    )
    op.drop_index("rebate_record_agent_idx", table_name="rebate_records")
    op.drop_index("account_invitation_agent_idx", table_name="account_invitations")
    op.drop_column("rebate_records", "agent_id")
    op.drop_column("account_invitations", "agent_id")
    op.drop_table("withdrawal_requests")
    op.drop_table("rebind_requests")
    op.drop_table("agent_wallets")
    op.drop_table("agents")
