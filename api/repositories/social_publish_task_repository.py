"""SocialPublishTask Repository Protocol.

Same isolation rule as SocialPublishAccount: every single-row read or write
constrains by ``tenant_id`` in SQL. The list query and the active-account
counter both filter on tenant.
"""

from collections.abc import Sequence
from typing import Any, Protocol

from models.social_publish import SocialPublishTask


class SocialPublishTaskRepository(Protocol):
    """Repository for ``social_publish_tasks``."""

    def create(
        self,
        *,
        tenant_id: str,
        account_id: str,
        platform: str,
        payload: dict[str, Any],
        created_by: str,
        work_id: str | None,
    ) -> SocialPublishTask:
        """Insert a new pending task; sau_task_id is filled in later."""
        ...

    def get_by_id_and_tenant(
        self,
        task_id: str,
        tenant_id: str,
        user_id: str | None = None,
    ) -> SocialPublishTask | None: ...

    def list_by_tenant(
        self,
        tenant_id: str,
        *,
        account_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        user_id: str | None = None,
    ) -> Sequence[SocialPublishTask]: ...

    def has_active_for_account(
        self,
        *,
        tenant_id: str,
        account_id: str,
        user_id: str | None = None,
    ) -> bool:
        """Return True if a task in ``ACTIVE_TASK_STATUSES`` exists for the
        ``(tenant_id, account_id)`` pair, optionally narrowed by ``user_id``
        (P8 per-member isolation). Used for single-flight enforcement —
        the same account+member cannot have two in-flight publishes.
        """
        ...

    def count_active_for_tenant(self, tenant_id: str) -> int:
        """Count tasks in ``ACTIVE_TASK_STATUSES`` for the tenant. Used by
        the P3 max-pending quota check so a single workspace can't fill the
        whole queue at the expense of other tenants."""
        ...

    def attach_sau_task_id(
        self,
        *,
        task_id: str,
        tenant_id: str,
        sau_task_id: str,
    ) -> SocialPublishTask | None:
        """Persist sau's celery id and flip status pending -> queued atomically."""
        ...

    def update_terminal(
        self,
        *,
        task_id: str,
        tenant_id: str,
        status: str,
        result_url: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> SocialPublishTask | None:
        """Mark a task terminal (success/failed). Idempotent — repeated calls
        with the same status are a no-op so concurrent pollers don't fight."""
        ...

    def update_status_to_running(
        self,
        *,
        task_id: str,
        tenant_id: str,
    ) -> SocialPublishTask | None:
        """Best-effort transition queued -> running while polling sau."""
        ...
