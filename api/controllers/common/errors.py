from werkzeug.exceptions import HTTPException

from libs.exception import BaseHTTPException


class FilenameNotExistsError(HTTPException):
    code = 400
    description = "The specified filename does not exist."


class RemoteFileUploadError(HTTPException):
    code = 400
    description = "Error uploading remote file."


class FileTooLargeError(BaseHTTPException):
    error_code = "file_too_large"
    description = "File size exceeded. {message}"
    code = 413


class UnsupportedFileTypeError(BaseHTTPException):
    error_code = "unsupported_file_type"
    description = "File type not allowed."
    code = 415


class BlockedFileExtensionError(BaseHTTPException):
    error_code = "file_extension_blocked"
    description = "The file extension is blocked for security reasons."
    code = 400


class TooManyFilesError(BaseHTTPException):
    error_code = "too_many_files"
    description = "Only one file is allowed."
    code = 400


class NoFileUploadedError(BaseHTTPException):
    error_code = "no_file_uploaded"
    description = "Please upload your file."
    code = 400


# ---------------------------------------------------------------------------
# Workflow budget gating — surfaces in console / web / service_api / explore
# ---------------------------------------------------------------------------


class InsufficientUserBudgetError(BaseHTTPException):
    """The caller's personal wallet is empty and ``check_can_run`` rejected the run.

    Description is Chinese-only: the frontend has no error-code mapping — it
    toasts ``response.description`` verbatim (see ``web/service/fetch.ts``
    ``afterResponseErrorCode``). The platform UI is Chinese throughout, so
    keeping the description in Chinese avoids an English flash for end users.
    """

    error_code = "insufficient_user_budget"
    description = "您的余额不足，无法启动本次运行。请联系工作区所有者为您分配额度。"
    code = 402  # Payment Required


class InsufficientTenantBudgetError(BaseHTTPException):
    """The workspace's allocated pool is exhausted and ``check_can_run`` rejected the run."""

    error_code = "insufficient_tenant_budget"
    description = "工作区已分配的额度池已耗尽。请联系工作区所有者充值并重新分配额度。"
    code = 402  # Payment Required


class InsufficientOwnerBudgetError(BaseHTTPException):
    """The workspace owner's spendable balance is exhausted.

    Distinct from ``InsufficientTenantBudgetError`` (member-facing): owners
    are the *only* ones who can fix this — telling them to "ask the owner to
    top up" is a UX dead-end. The owner spends from ``TenantBalance.balance``
    (the un-allocated pool); funds already moved into ``locked`` belong to
    members and can't be reclaimed by running workflows.
    """

    error_code = "insufficient_owner_budget"
    description = "工作区余额不足，无法启动本次运行。请先充值；已分配给成员的额度无法用于所有者自己的工作流。"
    code = 402  # Payment Required


def raise_workflow_budget_http_error(error_code: str) -> None:
    """Translate a ``WorkflowBudgetExceeded.code`` into the matching 402 HTTP error.

    Centralising the mapping avoids duplicating the if/else branch at every
    workflow entry point. The exception code strings are the contract between
    ``UserBillingService.check_can_run`` and the HTTP layer.
    """
    if error_code == "INSUFFICIENT_USER_BUDGET":
        raise InsufficientUserBudgetError()
    if error_code == "INSUFFICIENT_OWNER_BUDGET":
        raise InsufficientOwnerBudgetError()
    raise InsufficientTenantBudgetError()
