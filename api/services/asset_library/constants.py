"""Asset Library constants — MIME whitelist and asset-type enum.

The MIME whitelist is intentionally tighter than Dify's global file-upload
whitelist because asset-library files feed downstream into social publishing
flows (Douyin / Xiaohongshu / etc.) which only accept specific formats.
Extending the whitelist requires verifying the new format on every
downstream platform first.
"""

from enum import StrEnum


class AssetType(StrEnum):
    """The kind of asset a row in ``asset_libraries`` represents.

    File-type values (IMAGE/AUDIO/VIDEO) point at ``upload_files`` rows;
    PROMPT keeps its content inline. Used as the ``asset_type`` column
    value and as the dispatch key throughout the service layer.
    """

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    PROMPT = "prompt"


ALLOWED_MIME_BY_TYPE: dict[AssetType, frozenset[str]] = {
    AssetType.IMAGE: frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"}),
    AssetType.VIDEO: frozenset({"video/mp4", "video/quicktime"}),
    AssetType.AUDIO: frozenset({"audio/mpeg", "audio/mp4", "audio/wav"}),
}


def is_mime_allowed(asset_type: AssetType, mime: str) -> bool:
    """Return True if ``mime`` is permitted for ``asset_type``.

    Always returns False for ``AssetType.PROMPT`` (prompts are text-only).
    """
    allowed = ALLOWED_MIME_BY_TYPE.get(asset_type)
    return allowed is not None and mime in allowed
