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
    """The caller's personal wallet is empty and ``check_can_run`` rejected the run."""

    error_code = "insufficient_user_budget"
    description = (
        "Your wallet balance is not enough to start this run. "
        "Please ask your workspace owner to allocate funds."
    )
    code = 402  # Payment Required


class InsufficientTenantBudgetError(BaseHTTPException):
    """The workspace's allocated pool is exhausted and ``check_can_run`` rejected the run."""

    error_code = "insufficient_tenant_budget"
    description = (
        "The workspace allocated pool is exhausted. "
        "Please ask the workspace owner to top up and re-allocate."
    )
    code = 402  # Payment Required


def raise_workflow_budget_http_error(error_code: str) -> None:
    """Translate a ``WorkflowBudgetExceeded.code`` into the matching 402 HTTP error.

    Centralising the mapping avoids duplicating the if/else branch at every
    workflow entry point. The exception code strings are the contract between
    ``UserBillingService.check_can_run`` and the HTTP layer.
    """
    if error_code == "INSUFFICIENT_USER_BUDGET":
        raise InsufficientUserBudgetError()
    raise InsufficientTenantBudgetError()
