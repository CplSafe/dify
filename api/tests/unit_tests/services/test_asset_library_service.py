"""Unit tests for ``AssetLibraryService.create_prompt_asset`` and ``get_asset``.

The service layer is the only public entry point to ``asset_libraries`` and
must enforce two invariants:

- ``prompt_variables`` is validated through ``PromptVariableList`` and
  schema failures surface as ``InvalidPromptVariablesError`` (not raw
  Pydantic ``ValidationError`` — controllers catch the domain family).
- All reads are scoped by ``tenant_id`` end-to-end; cross-tenant access
  must raise ``AssetNotFoundError``, never return the row.

Tests follow the pure-mock pattern used by
``tests/unit_tests/services/tools/test_builtin_tools_manage_service.py``:
``Session`` is patched at the service module path and the inner session
mock is returned via ``__enter__``.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from models.asset_library import AssetLibrary
from services.asset_library.constants import AssetType
from services.asset_library.metadata_extractor import AudioMeta, VideoMeta
from services.asset_library_service import AssetLibraryService
from services.errors.asset_library import (
    AssetNotFoundError,
    InvalidPromptVariablesError,
    UnsupportedMimeTypeError,
)

MODULE = "services.asset_library_service"


def _mock_session(mock_session_cls: MagicMock) -> MagicMock:
    """Wire ``Session(...)`` to behave as a context manager around a mock."""
    session = MagicMock()
    mock_session_cls.return_value.__enter__ = MagicMock(return_value=session)
    mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)
    return session


def _make_user(account_id: str = "user-1") -> MagicMock:
    """Build an ``Account`` stand-in with the only field the service uses."""
    user = MagicMock()
    user.id = account_id
    return user


# ---------------------------------------------------------------------------
# create_prompt_asset
# ---------------------------------------------------------------------------


class TestCreatePromptAsset:
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_persists_validated_prompt_asset(self, mock_db, mock_session_cls):
        # Arrange
        session = _mock_session(mock_session_cls)
        prompt_variables = [
            {"name": "topic", "type": "string", "default": "AI"},
            {"name": "count", "type": "number", "default": 3},
        ]

        # Act
        result = AssetLibraryService.create_prompt_asset(
            tenant_id="tenant-a",
            user=_make_user("user-1"),
            name="Greeting prompt",
            content="Hello, {{topic}}!",
            prompt_variables=prompt_variables,
            description="a greeting",
            tags=["welcome", "demo"],
            category="marketing",
        )

        # Assert — return value
        assert isinstance(result, AssetLibrary)
        assert result.tenant_id == "tenant-a"
        assert result.created_by == "user-1"
        assert result.asset_type == AssetType.PROMPT
        assert result.name == "Greeting prompt"
        assert result.description == "a greeting"
        assert result.tags == ["welcome", "demo"]
        assert result.category == "marketing"
        assert result.content == "Hello, {{topic}}!"
        assert result.upload_file_id is None
        assert result.prompt_variables == [
            {"name": "topic", "type": "string", "default": "AI", "description": None},
            {"name": "count", "type": "number", "default": 3, "description": None},
        ]

        # Assert — persisted via session
        session.add.assert_called_once_with(result)
        session.commit.assert_called_once()

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_tags_input_is_copied_not_aliased(self, mock_db, mock_session_cls):
        """Caller mutating its own ``tags`` list after creation must not
        leak into the persisted asset row."""
        _mock_session(mock_session_cls)
        original_tags = ["a", "b"]

        result = AssetLibraryService.create_prompt_asset(
            tenant_id="tenant-a",
            user=_make_user(),
            name="x",
            content="y",
            prompt_variables=[],
            description=None,
            tags=original_tags,
            category=None,
        )

        original_tags.append("c")
        assert result.tags == ["a", "b"]

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_invalid_variable_name_raises_domain_error(self, mock_db, mock_session_cls):
        _mock_session(mock_session_cls)

        with pytest.raises(InvalidPromptVariablesError):
            AssetLibraryService.create_prompt_asset(
                tenant_id="tenant-a",
                user=_make_user(),
                name="x",
                content="y",
                prompt_variables=[{"name": "bad name!", "type": "string"}],
                description=None,
                tags=[],
                category=None,
            )

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_duplicate_variable_names_raise_domain_error(self, mock_db, mock_session_cls):
        _mock_session(mock_session_cls)

        with pytest.raises(InvalidPromptVariablesError):
            AssetLibraryService.create_prompt_asset(
                tenant_id="tenant-a",
                user=_make_user(),
                name="x",
                content="y",
                prompt_variables=[
                    {"name": "topic", "type": "string"},
                    {"name": "topic", "type": "number"},
                ],
                description=None,
                tags=[],
                category=None,
            )


# ---------------------------------------------------------------------------
# get_asset
# ---------------------------------------------------------------------------


class TestGetAsset:
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_returns_asset_for_matching_tenant(self, mock_db, mock_session_cls):
        # Arrange
        session = _mock_session(mock_session_cls)
        expected = MagicMock(spec=AssetLibrary)
        session.execute.return_value.scalar_one_or_none.return_value = expected

        # Act
        result = AssetLibraryService.get_asset("tenant-a", "asset-1")

        # Assert
        assert result is expected
        session.execute.assert_called_once()

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_cross_tenant_lookup_raises_asset_not_found(self, mock_db, mock_session_cls):
        """Repository scopes by ``tenant_id`` so a row that exists for
        tenant-b returns ``None`` for tenant-a — surfaced as
        ``AssetNotFoundError``."""
        session = _mock_session(mock_session_cls)
        session.execute.return_value.scalar_one_or_none.return_value = None

        with pytest.raises(AssetNotFoundError):
            AssetLibraryService.get_asset("tenant-a", "asset-belongs-to-tenant-b")

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_missing_id_raises_asset_not_found(self, mock_db, mock_session_cls):
        session = _mock_session(mock_session_cls)
        session.execute.return_value.scalar_one_or_none.return_value = None

        with pytest.raises(AssetNotFoundError):
            AssetLibraryService.get_asset("tenant-a", "does-not-exist")


# ---------------------------------------------------------------------------
# create_file_asset
# ---------------------------------------------------------------------------


def _png_bytes(width: int = 640, height: int = 480) -> bytes:
    """Render a real PNG of the requested dimensions for Pillow tests."""
    buf = BytesIO()
    Image.new("RGB", (width, height)).save(buf, format="PNG")
    return buf.getvalue()


def _make_upload(file_id: str = "up-id-1", size: int = 1234) -> MagicMock:
    """Build an ``UploadFile`` stand-in with the fields the service uses."""
    upload = MagicMock()
    upload.id = file_id
    upload.size = size
    return upload


class TestCreateFileAsset:
    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_image_happy_path(self, mock_db, mock_session_cls, mock_file_service_cls):
        # Arrange
        session = _mock_session(mock_session_cls)
        upload = _make_upload(file_id="up-id-1", size=1234)
        file_service = MagicMock()
        file_service.upload_file.return_value = upload
        mock_file_service_cls.return_value = file_service
        content = _png_bytes(640, 480)

        # Act
        result = AssetLibraryService.create_file_asset(
            tenant_id="tenant-a",
            user=_make_user("user-1"),
            file_content=content,
            filename="hello.png",
            mimetype="image/png",
            asset_type=AssetType.IMAGE,
            name="An image",
            description=None,
            tags=["a"],
            category=None,
        )

        # Assert — return value
        assert isinstance(result, AssetLibrary)
        assert result.tenant_id == "tenant-a"
        assert result.created_by == "user-1"
        assert result.asset_type == AssetType.IMAGE
        assert result.upload_file_id == "up-id-1"
        assert result.width == 640
        assert result.height == 480
        assert result.duration is None
        assert result.cover_url is None
        assert result.file_size == 1234

        # Assert — collaborators called
        file_service.upload_file.assert_called_once()
        session.add.assert_called_once_with(result)
        session.commit.assert_called_once()

    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_bad_mime_rejected_before_upload(self, mock_db, mock_session_cls, mock_file_service_cls):
        """``image/bmp`` is outside the asset-library whitelist; upload must
        not be attempted."""
        _mock_session(mock_session_cls)
        file_service = MagicMock()
        mock_file_service_cls.return_value = file_service

        with pytest.raises(UnsupportedMimeTypeError):
            AssetLibraryService.create_file_asset(
                tenant_id="tenant-a",
                user=_make_user(),
                file_content=b"x",
                filename="hello.bmp",
                mimetype="image/bmp",
                asset_type=AssetType.IMAGE,
                name="x",
                description=None,
                tags=[],
                category=None,
            )

        mock_file_service_cls.assert_not_called()
        file_service.upload_file.assert_not_called()

    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_wrong_asset_type_for_mime_rejected(self, mock_db, mock_session_cls, mock_file_service_cls):
        """``image/png`` is valid for IMAGE but not for AUDIO."""
        _mock_session(mock_session_cls)
        file_service = MagicMock()
        mock_file_service_cls.return_value = file_service

        with pytest.raises(UnsupportedMimeTypeError):
            AssetLibraryService.create_file_asset(
                tenant_id="tenant-a",
                user=_make_user(),
                file_content=b"x",
                filename="oops.png",
                mimetype="image/png",
                asset_type=AssetType.AUDIO,
                name="x",
                description=None,
                tags=[],
                category=None,
            )

        file_service.upload_file.assert_not_called()

    @patch(f"{MODULE}.extract_audio_metadata")
    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_audio_happy_path(
        self,
        mock_db,
        mock_session_cls,
        mock_file_service_cls,
        mock_extract_audio,
    ):
        _mock_session(mock_session_cls)
        upload = _make_upload(file_id="up-audio-1", size=4321)
        file_service = MagicMock()
        file_service.upload_file.return_value = upload
        mock_file_service_cls.return_value = file_service
        mock_extract_audio.return_value = AudioMeta(duration=12.34)

        result = AssetLibraryService.create_file_asset(
            tenant_id="tenant-a",
            user=_make_user("user-1"),
            file_content=b"audio-bytes",
            filename="clip.mp3",
            mimetype="audio/mpeg",
            asset_type=AssetType.AUDIO,
            name="A clip",
            description=None,
            tags=[],
            category=None,
        )

        assert result.asset_type == AssetType.AUDIO
        assert result.upload_file_id == "up-audio-1"
        assert result.duration == 12.34
        assert result.width is None
        assert result.height is None
        assert result.cover_url is None
        assert result.file_size == 4321

    @patch(f"{MODULE}.extract_video_cover")
    @patch(f"{MODULE}.extract_video_metadata")
    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_video_happy_path_uploads_cover(
        self,
        mock_db,
        mock_session_cls,
        mock_file_service_cls,
        mock_extract_video,
        mock_extract_cover,
    ):
        _mock_session(mock_session_cls)
        video_upload = _make_upload(file_id="up-video-1", size=9876)
        cover_upload = _make_upload(file_id="up-cover-1", size=222)
        file_service = MagicMock()
        # First call: video file. Second call: cover JPEG.
        file_service.upload_file.side_effect = [video_upload, cover_upload]
        mock_file_service_cls.return_value = file_service
        mock_extract_video.return_value = VideoMeta(width=1920, height=1080, duration=15.2)
        mock_extract_cover.return_value = b"jpegbytes"

        result = AssetLibraryService.create_file_asset(
            tenant_id="tenant-a",
            user=_make_user("user-1"),
            file_content=b"video-bytes",
            filename="movie.mp4",
            mimetype="video/mp4",
            asset_type=AssetType.VIDEO,
            name="A movie",
            description=None,
            tags=[],
            category=None,
        )

        assert result.asset_type == AssetType.VIDEO
        assert result.upload_file_id == "up-video-1"
        assert result.width == 1920
        assert result.height == 1080
        assert result.duration == 15.2
        assert result.file_size == 9876
        assert result.cover_url is not None
        assert "up-cover-1" in result.cover_url

        # FileService called twice — once for video, once for cover.
        assert file_service.upload_file.call_count == 2

    @patch(f"{MODULE}.extract_image_metadata")
    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_metadata_extraction_failure_is_best_effort(
        self,
        mock_db,
        mock_session_cls,
        mock_file_service_cls,
        mock_extract_image,
    ):
        """Extraction failure must NOT abort the upload — width/height
        persist as ``None`` and the asset row is committed."""
        _mock_session(mock_session_cls)
        upload = _make_upload(file_id="up-id-2", size=42)
        file_service = MagicMock()
        file_service.upload_file.return_value = upload
        mock_file_service_cls.return_value = file_service
        mock_extract_image.side_effect = RuntimeError("boom")

        result = AssetLibraryService.create_file_asset(
            tenant_id="tenant-a",
            user=_make_user(),
            file_content=b"not-really-png",
            filename="broken.png",
            mimetype="image/png",
            asset_type=AssetType.IMAGE,
            name="broken",
            description=None,
            tags=[],
            category=None,
        )

        assert isinstance(result, AssetLibrary)
        assert result.upload_file_id == "up-id-2"
        assert result.width is None
        assert result.height is None
        assert result.file_size == 42
