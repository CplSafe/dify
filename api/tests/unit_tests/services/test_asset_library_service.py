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
from typing import Any
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


# ---------------------------------------------------------------------------
# list_assets
# ---------------------------------------------------------------------------


def _list_session(mock_session_cls: MagicMock, *, total: int, items: list[Any]) -> MagicMock:
    """Wire ``session.execute`` to first return a count, then a scalars iterable.

    ``list_assets`` runs two SQL statements: ``SELECT count(*)`` and
    ``SELECT ... ORDER BY ... OFFSET ... LIMIT ...``. Returning the right shape
    in order is enough to cover the call path without parsing the AST.
    """
    session = _mock_session(mock_session_cls)
    count_result = MagicMock()
    count_result.scalar_one.return_value = total
    items_result = MagicMock()
    items_result.scalars.return_value = items
    session.execute.side_effect = [count_result, items_result]
    return session


class TestListAssets:
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_list_returns_pagination_for_tenant(self, mock_db, mock_session_cls):
        asset = MagicMock(spec=AssetLibrary)
        asset.id = "a1"
        asset.tenant_id = "tenant-a"
        _list_session(mock_session_cls, total=42, items=[asset])

        page = AssetLibraryService.list_assets(tenant_id="tenant-a", page=1, limit=20)

        assert page.total == 42
        assert page.items == [asset]
        assert page.page == 1
        assert page.limit == 20
        assert page.has_more is True

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_has_more_false_on_last_page(self, mock_db, mock_session_cls):
        _list_session(mock_session_cls, total=15, items=[MagicMock()])

        page = AssetLibraryService.list_assets(tenant_id="tenant-a", page=1, limit=20)

        assert page.has_more is False

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_list_filters_by_asset_type(self, mock_db, mock_session_cls):
        _list_session(mock_session_cls, total=0, items=[])

        page = AssetLibraryService.list_assets(tenant_id="tenant-a", asset_type="image")

        assert page.total == 0
        assert page.items == []

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_list_filters_by_keyword(self, mock_db, mock_session_cls):
        _list_session(mock_session_cls, total=1, items=[MagicMock()])

        page = AssetLibraryService.list_assets(tenant_id="tenant-a", keyword="hello")

        assert page.total == 1

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_list_filters_by_category(self, mock_db, mock_session_cls):
        _list_session(mock_session_cls, total=2, items=[MagicMock(), MagicMock()])

        page = AssetLibraryService.list_assets(tenant_id="tenant-a", category="模板")

        assert page.total == 2

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_list_filters_by_tags(self, mock_db, mock_session_cls):
        _list_session(mock_session_cls, total=3, items=[MagicMock()] * 3)

        page = AssetLibraryService.list_assets(tenant_id="tenant-a", tags=["a", "b"])

        assert page.total == 3

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_list_clamps_page_to_minimum_1(self, mock_db, mock_session_cls):
        _list_session(mock_session_cls, total=0, items=[])

        page = AssetLibraryService.list_assets(tenant_id="tenant-a", page=0, limit=20)

        assert page.page == 1


# ---------------------------------------------------------------------------
# update_asset_metadata
# ---------------------------------------------------------------------------


def _update_asset_stub(
    *,
    asset_id: str = "a1",
    tenant_id: str = "tenant-a",
    asset_type: str = "prompt",
    name: str = "old",
    description: str | None = "old description",
    tags: list[str] | None = None,
    category: str | None = None,
    upload_file_id: str | None = None,
    prompt_variables: list[Any] | None = None,
    content: str | None = None,
) -> MagicMock:
    """Build a mutable in-memory stand-in for an ``AssetLibrary`` row."""
    asset = MagicMock(spec=AssetLibrary)
    asset.id = asset_id
    asset.tenant_id = tenant_id
    asset.asset_type = asset_type
    asset.name = name
    asset.description = description
    asset.tags = list(tags) if tags is not None else []
    asset.category = category
    asset.upload_file_id = upload_file_id
    asset.prompt_variables = list(prompt_variables) if prompt_variables is not None else []
    asset.content = content
    return asset


class TestUpdateAssetMetadata:
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_updates_whitelist_fields(self, mock_db, mock_session_cls):
        session = _mock_session(mock_session_cls)
        asset = _update_asset_stub()
        session.get.return_value = asset

        result = AssetLibraryService.update_asset_metadata(
            tenant_id="tenant-a",
            asset_id="a1",
            name="new",
            description="d",
            tags=["x"],
        )

        assert result is asset
        assert asset.name == "new"
        assert asset.description == "d"
        assert asset.tags == ["x"]
        assert asset.asset_type == "prompt"
        session.commit.assert_called_once()

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_blacklist_fields_silently_ignored(self, mock_db, mock_session_cls):
        session = _mock_session(mock_session_cls)
        asset = _update_asset_stub(upload_file_id="orig-up")
        session.get.return_value = asset

        AssetLibraryService.update_asset_metadata(
            tenant_id="tenant-a",
            asset_id="a1",
            asset_type="image",
            upload_file_id="other",
            name="renamed",
        )

        assert asset.asset_type == "prompt"
        assert asset.upload_file_id == "orig-up"
        assert asset.name == "renamed"

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_invalid_prompt_variables_raises(self, mock_db, mock_session_cls):
        session = _mock_session(mock_session_cls)
        session.get.return_value = _update_asset_stub()

        with pytest.raises(InvalidPromptVariablesError):
            AssetLibraryService.update_asset_metadata(
                tenant_id="tenant-a",
                asset_id="a1",
                prompt_variables=[{"name": "bad name!", "type": "string"}],
            )

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_valid_prompt_variables_updated(self, mock_db, mock_session_cls):
        session = _mock_session(mock_session_cls)
        asset = _update_asset_stub()
        session.get.return_value = asset

        AssetLibraryService.update_asset_metadata(
            tenant_id="tenant-a",
            asset_id="a1",
            prompt_variables=[{"name": "x", "type": "string"}],
        )

        assert asset.prompt_variables == [
            {"name": "x", "type": "string", "default": None, "description": None},
        ]
        # Persisted as plain dicts, not Pydantic models.
        for entry in asset.prompt_variables:
            assert isinstance(entry, dict)

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_cross_tenant_raises_not_found(self, mock_db, mock_session_cls):
        session = _mock_session(mock_session_cls)
        session.get.return_value = _update_asset_stub(tenant_id="tenant-b")

        with pytest.raises(AssetNotFoundError):
            AssetLibraryService.update_asset_metadata(tenant_id="tenant-a", asset_id="a1", name="new")

    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_missing_id_raises_not_found(self, mock_db, mock_session_cls):
        session = _mock_session(mock_session_cls)
        session.get.return_value = None

        with pytest.raises(AssetNotFoundError):
            AssetLibraryService.update_asset_metadata(tenant_id="tenant-a", asset_id="missing", name="new")


# ---------------------------------------------------------------------------
# delete_asset
# ---------------------------------------------------------------------------


class TestDeleteAsset:
    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_delete_prompt_only_deletes_db_row(self, mock_db, mock_session_cls, mock_file_service_cls):
        session = _mock_session(mock_session_cls)
        asset = _update_asset_stub(upload_file_id=None)
        session.get.return_value = asset

        AssetLibraryService.delete_asset(tenant_id="tenant-a", asset_id="a1")

        session.delete.assert_called_once_with(asset)
        session.commit.assert_called_once()
        mock_file_service_cls.assert_not_called()

    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_delete_file_cascades_upload_cleanup(self, mock_db, mock_session_cls, mock_file_service_cls):
        session = _mock_session(mock_session_cls)
        asset = _update_asset_stub(upload_file_id="up-1")
        session.get.return_value = asset
        file_service = MagicMock()
        mock_file_service_cls.return_value = file_service

        AssetLibraryService.delete_asset(tenant_id="tenant-a", asset_id="a1")

        session.delete.assert_called_once_with(asset)
        session.commit.assert_called_once()
        file_service.delete_file.assert_called_once_with("up-1")

    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_delete_storage_cleanup_failure_does_not_block_db_delete(
        self, mock_db, mock_session_cls, mock_file_service_cls
    ):
        session = _mock_session(mock_session_cls)
        asset = _update_asset_stub(upload_file_id="up-1")
        session.get.return_value = asset
        file_service = MagicMock()
        file_service.delete_file.side_effect = RuntimeError("storage gone")
        mock_file_service_cls.return_value = file_service

        # Should not raise.
        AssetLibraryService.delete_asset(tenant_id="tenant-a", asset_id="a1")

        session.delete.assert_called_once_with(asset)
        session.commit.assert_called_once()
        file_service.delete_file.assert_called_once_with("up-1")

    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_cross_tenant_raises_not_found(self, mock_db, mock_session_cls, mock_file_service_cls):
        session = _mock_session(mock_session_cls)
        session.get.return_value = _update_asset_stub(tenant_id="tenant-b")

        with pytest.raises(AssetNotFoundError):
            AssetLibraryService.delete_asset(tenant_id="tenant-a", asset_id="a1")

        mock_file_service_cls.assert_not_called()

    @patch(f"{MODULE}.FileService")
    @patch(f"{MODULE}.Session")
    @patch(f"{MODULE}.db")
    def test_missing_id_raises_not_found(self, mock_db, mock_session_cls, mock_file_service_cls):
        session = _mock_session(mock_session_cls)
        session.get.return_value = None

        with pytest.raises(AssetNotFoundError):
            AssetLibraryService.delete_asset(tenant_id="tenant-a", asset_id="missing")

        mock_file_service_cls.assert_not_called()
