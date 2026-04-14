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
