"""Domain exceptions for wallet operations.

Each exception carries a stable ``code`` used by controllers to map to
user-facing error messages without exposing service internals.
"""


class WalletError(Exception):
    """Base exception for wallet operations."""

    code = "WALLET_ERROR"


class InsufficientTenantBalance(WalletError):  # noqa: N818
    """Raised when the tenant's unallocated balance cannot cover an allocation."""

    code = "ALLOCATION_EXCEEDS_BALANCE"


class InsufficientMemberBalance(WalletError):  # noqa: N818
    """Raised when a reclaim amount exceeds the member's current balance."""

    code = "RECLAIM_EXCEEDS_MEMBER_BALANCE"


class NotTenantMember(WalletError):  # noqa: N818
    """Raised when the target account is not a member of the tenant."""

    code = "NOT_TENANT_MEMBER"


class AllocateToOwnerNotAllowed(WalletError):  # noqa: N818
    """Raised when allocate/reclaim targets the tenant owner.

    Owners consume workspace funds directly from ``TenantBalance.balance``
    — they never hold a per-member ``UserBalance`` pool. Trying to
    allocate to or reclaim from the owner would break the invariant
    ``Σ(UserBalance.balance for members) == TenantBalance.locked``.
    """

    code = "ALLOCATE_TO_OWNER_NOT_ALLOWED"


class WorkflowBudgetExceeded(WalletError):  # noqa: N818
    """Raised at the workflow entry gate when no wallet can fund the run.

    ``code`` is one of:
    - ``"INSUFFICIENT_USER_BUDGET"`` — caller's personal balance ≤ 0
    - ``"INSUFFICIENT_TENANT_BUDGET"`` — workspace allocated pool exhausted

    The error_code matches what ``UserBillingService.check_can_run`` returns,
    so callers can pass it through verbatim to the HTTP layer.
    """

    def __init__(self, error_code: str, message: str = ""):
        super().__init__(message or error_code)
        self.code = error_code
