"""SocialPublishAccount Repository Protocol.

Defines the service-layer interface for `social_publish_accounts`. All methods
that touch a single row enforce tenant isolation by including `tenant_id` in
the SQL `WHERE` clause — service layer MUST pass the caller's tenant_id.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from models.social_publish import SocialPublishAccount


class SocialPublishAccountRepository(Protocol):
    """Repository for `social_publish_accounts`."""

    def create(
        self,
        *,
        tenant_id: str,
        platform: str,
        sau_account_id: str,
        display_name: str | None,
        avatar_url: str | None,
        status: str,
        created_by: str,
    ) -> SocialPublishAccount:
        """Insert a new row and return it."""
        ...

    def get_by_id_and_tenant(
        self,
        account_id: str,
        tenant_id: str,
    ) -> SocialPublishAccount | None:
        """Return a row only if it belongs to the given tenant."""
        ...

    def get_by_sau_account_id(
        self,
        sau_account_id: str,
    ) -> SocialPublishAccount | None:
        """Look up by the sau-side id.

        This is the ONLY method that bypasses tenant scoping. Callers must
        re-check `obj.tenant_id` before acting on the result.
        """
        ...

    def list_by_tenant(
        self,
        tenant_id: str,
        platform: str | None = None,
    ) -> Sequence[SocialPublishAccount]:
        """List all accounts visible to this tenant, newest first."""
        ...

    def update_status(
        self,
        *,
        account_id: str,
        tenant_id: str,
        status: str,
        last_check_at: datetime | None = None,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> SocialPublishAccount | None:
        """Partial update.

        Returns the updated row, or None if the `(account_id, tenant_id)` pair
        did not match. Callers treat None as a permission failure.
        """
        ...

    def delete_by_id_and_tenant(
        self,
        account_id: str,
        tenant_id: str,
    ) -> bool:
        """Delete a row and return True if a row was actually removed."""
        ...
