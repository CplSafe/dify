import pytest

from controllers.common.errors import (
    BlockedFileExtensionError,
    FilenameNotExistsError,
    FileTooLargeError,
    InsufficientOwnerBudgetError,
    InsufficientTenantBudgetError,
    InsufficientUserBudgetError,
    NoFileUploadedError,
    RemoteFileUploadError,
    TooManyFilesError,
    UnsupportedFileTypeError,
    raise_workflow_budget_http_error,
)


class TestFilenameNotExistsError:
    def test_defaults(self):
        error = FilenameNotExistsError()

        assert error.code == 400
        assert error.description == "The specified filename does not exist."


class TestRemoteFileUploadError:
    def test_defaults(self):
        error = RemoteFileUploadError()

        assert error.code == 400
        assert error.description == "Error uploading remote file."


class TestFileTooLargeError:
    def test_defaults(self):
        error = FileTooLargeError()

        assert error.code == 413
        assert error.error_code == "file_too_large"
        assert error.description == "File size exceeded. {message}"


class TestUnsupportedFileTypeError:
    def test_defaults(self):
        error = UnsupportedFileTypeError()

        assert error.code == 415
        assert error.error_code == "unsupported_file_type"
        assert error.description == "File type not allowed."


class TestBlockedFileExtensionError:
    def test_defaults(self):
        error = BlockedFileExtensionError()

        assert error.code == 400
        assert error.error_code == "file_extension_blocked"
        assert error.description == "The file extension is blocked for security reasons."


class TestTooManyFilesError:
    def test_defaults(self):
        error = TooManyFilesError()

        assert error.code == 400
        assert error.error_code == "too_many_files"
        assert error.description == "Only one file is allowed."


class TestNoFileUploadedError:
    def test_defaults(self):
        error = NoFileUploadedError()

        assert error.code == 400
        assert error.error_code == "no_file_uploaded"
        assert error.description == "Please upload your file."


class TestInsufficientUserBudgetError:
    def test_defaults(self):
        error = InsufficientUserBudgetError()

        assert error.code == 402
        assert error.error_code == "insufficient_user_budget"


class TestInsufficientTenantBudgetError:
    def test_defaults(self):
        error = InsufficientTenantBudgetError()

        assert error.code == 402
        assert error.error_code == "insufficient_tenant_budget"


class TestInsufficientOwnerBudgetError:
    def test_defaults(self):
        error = InsufficientOwnerBudgetError()

        assert error.code == 402
        assert error.error_code == "insufficient_owner_budget"


class TestRaiseWorkflowBudgetHttpError:
    """Contract: every ``WorkflowBudgetExceeded.code`` from
    ``UserBillingService.check_can_run`` maps to a distinct 402 HTTPException.

    The owner code must NOT collapse into the tenant code — owners need a
    different message ("top up" vs "ask the owner to top up").
    """

    def test_user_code_raises_user_error(self):
        with pytest.raises(InsufficientUserBudgetError):
            raise_workflow_budget_http_error("INSUFFICIENT_USER_BUDGET")

    def test_owner_code_raises_owner_error(self):
        with pytest.raises(InsufficientOwnerBudgetError):
            raise_workflow_budget_http_error("INSUFFICIENT_OWNER_BUDGET")

    def test_tenant_code_raises_tenant_error(self):
        with pytest.raises(InsufficientTenantBudgetError):
            raise_workflow_budget_http_error("INSUFFICIENT_TENANT_BUDGET")

    def test_unknown_code_falls_back_to_tenant_error(self):
        # Defensive default: an unknown code shouldn't crash the request
        # handler with a NameError; surface the most generic 402 instead.
        with pytest.raises(InsufficientTenantBudgetError):
            raise_workflow_budget_http_error("SOMETHING_NEW")
