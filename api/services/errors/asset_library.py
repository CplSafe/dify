"""Domain exceptions for the Asset Library feature.

Raised by ``AssetLibraryService`` and translated to HTTP responses by the
controllers in ``controllers/console/asset_library/``. All concrete classes
inherit from ``AssetLibraryError`` so callers can catch the family at module
boundaries.
"""


class AssetLibraryError(Exception):
    """Base class for asset-library domain errors."""


class UnsupportedMimeTypeError(AssetLibraryError):
    """Uploaded file's MIME type is outside the asset-library whitelist."""

    mime: str

    def __init__(self, mime: str) -> None:
        super().__init__(f"Unsupported MIME type: {mime}")
        self.mime = mime


class FileSizeLimitExceededError(AssetLibraryError):
    """Uploaded file exceeds the configured size limit."""


class InvalidPromptVariablesError(AssetLibraryError):
    """`prompt_variables` payload failed schema validation."""


class AssetNotFoundError(AssetLibraryError):
    """Requested asset does not exist for the current tenant."""
