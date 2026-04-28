"""Unit tests for AssetType enum + MIME whitelist."""

import pytest

from services.asset_library.constants import (
    ALLOWED_MIME_BY_TYPE,
    AssetType,
    is_mime_allowed,
)


@pytest.mark.parametrize(
    ("asset_type", "mime", "expected"),
    [
        (AssetType.IMAGE, "image/jpeg", True),
        (AssetType.IMAGE, "image/png", True),
        (AssetType.IMAGE, "image/webp", True),
        (AssetType.IMAGE, "image/gif", True),
        (AssetType.IMAGE, "image/bmp", False),
        (AssetType.VIDEO, "video/mp4", True),
        (AssetType.VIDEO, "video/quicktime", True),
        (AssetType.VIDEO, "video/avi", False),
        (AssetType.AUDIO, "audio/mpeg", True),
        (AssetType.AUDIO, "audio/mp4", True),
        (AssetType.AUDIO, "audio/wav", True),
        (AssetType.AUDIO, "audio/ogg", False),
    ],
)
def test_is_mime_allowed(asset_type, mime, expected):
    assert is_mime_allowed(asset_type, mime) is expected


def test_prompt_type_has_no_mime_whitelist():
    assert AssetType.PROMPT not in ALLOWED_MIME_BY_TYPE


def test_prompt_type_always_rejected_for_mime_check():
    assert is_mime_allowed(AssetType.PROMPT, "text/plain") is False


def test_asset_type_string_values():
    assert AssetType.IMAGE.value == "image"
    assert AssetType.AUDIO.value == "audio"
    assert AssetType.VIDEO.value == "video"
    assert AssetType.PROMPT.value == "prompt"
