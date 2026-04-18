"""remove ks (Kuaishou) rows from social_publish_accounts and tasks

Revision ID: 8664648137a4
Revises: 5a63370576c2
Create Date: 2026-04-19 10:00:00.000000

P5 drops Kuaishou support entirely. Upstream social-auto-upload never
shipped a ``ks_cookie_gen`` so the auth flow could not complete; the
publish flow would fast-fail at cookie load. This migration removes any
``platform = 'ks'`` rows that may have been seeded during P4 — in
practice the P4 FE allowlist never let users add ks accounts, so this
is expected to be a no-op in most environments. The migration is here
to make the contract explicit.

The ``SocialPublishPlatform.KS`` enum value is intentionally NOT
removed from the model layer:

- PostgreSQL ENUM modification is a multi-step operation that is hard
  to roll back if the migration is interrupted.
- Keeping the enum value lets the DB read any historical row that
  somehow escapes this DELETE without the SQLAlchemy model raising on
  ``platform_enum``.
- New rows can no longer reach ``ks`` because the application-layer
  ``SUPPORTED_PLATFORMS_*`` allowlists rejected it.

"""

from alembic import op

revision = "8664648137a4"
down_revision = "5a63370576c2"
branch_labels = None
depends_on = None


def upgrade():
    # Tasks first so the FK from task → account stays consistent if a
    # future migration ever adds one (currently the schema only has a
    # logical reference).
    op.execute("DELETE FROM social_publish_tasks WHERE platform = 'ks'")
    op.execute("DELETE FROM social_publish_accounts WHERE platform = 'ks'")


def downgrade():
    # No-op: we cannot reconstruct deleted ks rows. Re-enabling KS in
    # the future will re-introduce the platform via a new account
    # creation flow, not via downgrade.
    pass
