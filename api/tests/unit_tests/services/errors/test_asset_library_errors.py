"""Unit tests for asset-library domain exceptions."""

from services.errors.asset_library import (
    AssetLibraryError,
    AssetNotFoundError,
    FileSizeLimitExceededError,
    InvalidPromptVariablesError,
    UnsupportedMimeTypeError,
)


def test_error_hierarchy():
    for cls in [
        UnsupportedMimeTypeError,
        InvalidPromptVariablesError,
        AssetNotFoundError,
        FileSizeLimitExceededError,
    ]:
        assert issubclass(cls, AssetLibraryError)


def test_unsupported_mime_carries_mime_attr():
    err = UnsupportedMimeTypeError("video/avi")
    assert err.mime == "video/avi"
    assert "video/avi" in str(err)
