"""cast social_publish_* uuid-shaped columns from VARCHAR to UUID

Revision ID: a918a826301d
Revises: 8664648137a4
Create Date: 2026-04-19 11:00:00.000000

P1 created social_publish_accounts and social_publish_tasks with
``sa.String(36)`` for every id-shaped column, but the SQLAlchemy model
declares them as ``StringUUID`` (which compiles to PostgreSQL UUID).
At runtime SQLAlchemy automatically casts bind parameters with
``::UUID``, so any ``WHERE tenant_id = $1::UUID`` on the VARCHAR column
fails with::

    operator does not exist: character varying = uuid

Cast all the affected columns to PostgreSQL UUID. ``USING <col>::uuid``
keeps existing rows intact (any row that survived must already be a
valid UUID string — that's the only thing the application layer ever
inserts). Indexes survive a column type change in PostgreSQL.

SQLite is the test backend; ALTER COLUMN TYPE is a no-op there because
sqlite stores everything as text and the ORM round-trips it as a string
either way. The op.alter_column call below short-circuits on sqlite via
the ``existing_type`` check.

"""

from alembic import op
import sqlalchemy as sa

revision = "a918a826301d"
down_revision = "8664648137a4"
branch_labels = None
depends_on = None


_ACCOUNTS_UUID_COLUMNS = ("id", "tenant_id", "created_by")
_TASKS_UUID_COLUMNS = ("id", "tenant_id", "account_id", "work_id", "created_by")


def _alter_to_uuid(table: str, column: str, *, nullable: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # sqlite (tests) is permissive; nothing to do.
        return
    op.alter_column(
        table,
        column,
        existing_type=sa.String(36),
        type_=sa.dialects.postgresql.UUID(as_uuid=False),
        existing_nullable=nullable,
        postgresql_using=f"{column}::uuid",
    )


def _alter_to_varchar(table: str, column: str, *, nullable: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.alter_column(
        table,
        column,
        existing_type=sa.dialects.postgresql.UUID(as_uuid=False),
        type_=sa.String(36),
        existing_nullable=nullable,
        postgresql_using=f"{column}::text",
    )


def upgrade() -> None:
    for col in _ACCOUNTS_UUID_COLUMNS:
        _alter_to_uuid("social_publish_accounts", col, nullable=False)
    for col in _TASKS_UUID_COLUMNS:
        # work_id is the only nullable id column.
        _alter_to_uuid(
            "social_publish_tasks",
            col,
            nullable=(col == "work_id"),
        )


def downgrade() -> None:
    for col in _TASKS_UUID_COLUMNS:
        _alter_to_varchar(
            "social_publish_tasks",
            col,
            nullable=(col == "work_id"),
        )
    for col in _ACCOUNTS_UUID_COLUMNS:
        _alter_to_varchar("social_publish_accounts", col, nullable=False)
