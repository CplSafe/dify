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

from unittest.mock import MagicMock, patch

import pytest

from models.asset_library import AssetLibrary
from services.asset_library.constants import AssetType
from services.asset_library_service import AssetLibraryService
from services.errors.asset_library import (
    AssetNotFoundError,
    InvalidPromptVariablesError,
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
