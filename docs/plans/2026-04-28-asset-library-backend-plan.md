# 素材库（Asset Library）后端实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 Dify 素材库后端 —— 租户共享的资产管理（图片/音频/视频/提示词），复用 `FileService` + `upload_files` 表，新增 `asset_libraries` 表 + `AssetLibraryService` + `/console/api/asset-library` 端点。

**Architecture:** 三层（controller → service → model），同步抽帧（ffmpeg/ffprobe），租户隔离通过所有 service 方法首参强制 `tenant_id`。文件类素材物理存储复用 Dify 现有 storage 抽象（local/S3/OSS），不重复造。

**Tech Stack:** Python 3.12+, Flask + flask-restful, SQLAlchemy 2.0 (Mapped style), Pydantic v2, Alembic, pytest, uv 包管理；新增依赖 `mutagen`；系统二进制 `ffmpeg` / `ffprobe`。

**Reference design:** [`docs/plans/2026-04-28-asset-library-design.md`](./2026-04-28-asset-library-design.md)

**Code standards:** 严格遵守 `api/AGENTS.md`：
- 使用 `logger = logging.getLogger(__name__)`，禁 `print`
- 模型继承 `models.base.TypeBase`
- Pydantic v2 + `ConfigDict(extra="forbid")`
- 行宽 ≤ 120 字符
- 通过 `uv run --project api` 跑命令
- 通过 `make format` / `make lint` / `make type-check` 检查

---

## Phase 1：数据层

### Task 1：新增 `AssetLibrary` 模型

**Files:**
- Create: `api/models/asset_library.py`
- Test: `api/tests/unit_tests/models/test_asset_library.py`

**Step 1: Write the failing test**

```python
# api/tests/unit_tests/models/test_asset_library.py
"""Smoke test that AssetLibrary model is importable and has expected columns."""
from models.asset_library import AssetLibrary


def test_asset_library_has_required_columns():
    cols = {c.name for c in AssetLibrary.__table__.columns}
    required = {
        "id", "tenant_id", "created_by", "asset_type",
        "name", "description", "tags", "category",
        "upload_file_id", "cover_url", "duration", "width", "height", "file_size",
        "content", "prompt_variables",
        "created_at", "updated_at",
    }
    assert required.issubset(cols)


def test_asset_library_table_name():
    assert AssetLibrary.__tablename__ == "asset_libraries"


def test_asset_library_index_present():
    index_names = {idx.name for idx in AssetLibrary.__table__.indexes}
    assert "idx_asset_lib_tenant_type_created" in index_names
```

**Step 2: Run test to verify it fails**

Run: `uv run --project api pytest api/tests/unit_tests/models/test_asset_library.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models.asset_library'`

**Step 3: Write minimal implementation**

```python
# api/models/asset_library.py
"""
Asset Library model.

A tenant-shared asset management layer. Files (image/audio/video) reuse
Dify's `upload_files` table via `upload_file_id`; prompts store text in `content`.

Tenant isolation is enforced by every service-layer query — no FK to tenants;
no FK to `upload_files` (consistent with Dify's loose-coupling convention).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base
from models.types import StringUUID


class AssetLibrary(Base):
    """ORM model for the `asset_libraries` table."""

    __tablename__ = "asset_libraries"

    id: Mapped[str] = mapped_column(
        StringUUID, server_default=func.gen_random_uuid(), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(StringUUID, nullable=False)

    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # 'image' | 'audio' | 'video' | 'prompt'

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    # File assets (NULL for prompts)
    upload_file_id: Mapped[Optional[str]] = mapped_column(StringUUID)
    cover_url: Mapped[Optional[str]] = mapped_column(String(512))
    duration: Mapped[Optional[float]] = mapped_column(Float)  # seconds
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)

    # Prompt assets (NULL for files)
    content: Mapped[Optional[str]] = mapped_column(Text)
    prompt_variables: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_asset_lib_tenant_type_created", "tenant_id", "asset_type", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"AssetLibrary(id={self.id!r}, tenant_id={self.tenant_id!r}, "
            f"asset_type={self.asset_type!r}, name={self.name!r})"
        )
```

> Verify the actual base class import path: existing models use `from models.base import Base` or similar. Check `api/models/base.py` and a sibling like `api/models/creator_task.py` to confirm the canonical import. If the project uses `TypeBase`, swap accordingly.

**Step 4: Run test to verify it passes**

Run: `uv run --project api pytest api/tests/unit_tests/models/test_asset_library.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add api/models/asset_library.py api/tests/unit_tests/models/test_asset_library.py
git commit -m "feat(asset-library): add AssetLibrary ORM model"
```

---

### Task 2：Alembic 迁移

**Files:**
- Create: `api/migrations/versions/<auto_hash>_add_asset_libraries.py`

**Step 1: Generate migration scaffold**

Run: `uv run --project api flask db revision -m "add asset_libraries"`
Expected: a new file appears under `api/migrations/versions/`

**Step 2: Edit the generated file** to fill in `upgrade()` and `downgrade()`:

```python
"""add asset_libraries

Revision ID: <auto>
Revises: <auto>
Create Date: 2026-04-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "<auto>"
down_revision = "<auto>"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "asset_libraries",
        sa.Column("id", postgresql.UUID(as_uuid=False), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("asset_type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("upload_file_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("cover_url", sa.String(length=512), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("prompt_variables", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asset_libraries_tenant_id", "asset_libraries", ["tenant_id"])
    op.create_index("ix_asset_libraries_category", "asset_libraries", ["category"])
    op.create_index(
        "idx_asset_lib_tenant_type_created",
        "asset_libraries",
        ["tenant_id", "asset_type", "created_at"],
    )


def downgrade():
    op.drop_index("idx_asset_lib_tenant_type_created", table_name="asset_libraries")
    op.drop_index("ix_asset_libraries_category", table_name="asset_libraries")
    op.drop_index("ix_asset_libraries_tenant_id", table_name="asset_libraries")
    op.drop_table("asset_libraries")
```

**Step 3: Apply migration locally**

Run: `uv run --project api flask db upgrade`
Expected: stdout shows `Running upgrade ... -> <auto>, add asset_libraries`

**Step 4: Verify schema**

Run:
```bash
docker exec -it dify-postgres psql -U postgres -d dify -c "\d asset_libraries"
```
Expected: table exists with columns and 3 indexes.

**Step 5: Commit**

```bash
git add api/migrations/versions/<auto>_add_asset_libraries.py
git commit -m "feat(asset-library): add asset_libraries migration"
```

---

## Phase 2：Service 层

### Task 3：错误类

**Files:**
- Create: `api/services/errors/asset_library.py`

**Step 1: Write the failing test**

```python
# api/tests/unit_tests/services/errors/test_asset_library_errors.py
import pytest

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


def test_unsupported_mime_carries_message():
    err = UnsupportedMimeTypeError("video/avi")
    assert "video/avi" in str(err)
```

**Step 2: Run test to verify it fails**

Run: `uv run --project api pytest api/tests/unit_tests/services/errors/test_asset_library_errors.py -v`
Expected: FAIL `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# api/services/errors/asset_library.py
"""Domain exceptions for the Asset Library feature."""


class AssetLibraryError(Exception):
    """Base class for asset-library domain errors."""


class UnsupportedMimeTypeError(AssetLibraryError):
    """Raised when an uploaded file's MIME type is outside the asset-library whitelist."""

    def __init__(self, mime: str) -> None:
        super().__init__(f"Unsupported MIME type: {mime}")
        self.mime = mime


class FileSizeLimitExceededError(AssetLibraryError):
    """Raised when the uploaded file exceeds the configured size limit."""


class InvalidPromptVariablesError(AssetLibraryError):
    """Raised when `prompt_variables` payload fails schema validation."""


class AssetNotFoundError(AssetLibraryError):
    """Raised when the requested asset does not exist for the tenant."""
```

**Step 4: Run test to verify it passes**

Run: `uv run --project api pytest api/tests/unit_tests/services/errors/test_asset_library_errors.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/services/errors/asset_library.py api/tests/unit_tests/services/errors/test_asset_library_errors.py
git commit -m "feat(asset-library): add domain exception classes"
```

---

### Task 4：MIME 白名单常量 + 校验

**Files:**
- Create: `api/services/asset_library/__init__.py`
- Create: `api/services/asset_library/constants.py`
- Test: `api/tests/unit_tests/services/asset_library/test_constants.py`

**Step 1: Write the failing test**

```python
# api/tests/unit_tests/services/asset_library/test_constants.py
import pytest

from services.asset_library.constants import (
    ALLOWED_MIME_BY_TYPE,
    AssetType,
    is_mime_allowed,
)


@pytest.mark.parametrize("asset_type, mime, ok", [
    (AssetType.IMAGE, "image/jpeg", True),
    (AssetType.IMAGE, "image/png", True),
    (AssetType.IMAGE, "image/bmp", False),
    (AssetType.VIDEO, "video/mp4", True),
    (AssetType.VIDEO, "video/avi", False),
    (AssetType.AUDIO, "audio/mpeg", True),
    (AssetType.AUDIO, "audio/ogg", False),
])
def test_is_mime_allowed(asset_type, mime, ok):
    assert is_mime_allowed(asset_type, mime) is ok


def test_prompt_type_has_no_mime():
    assert AssetType.PROMPT not in ALLOWED_MIME_BY_TYPE
```

**Step 2: Run test to verify it fails**

Run: `uv run --project api pytest api/tests/unit_tests/services/asset_library/test_constants.py -v`
Expected: FAIL `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# api/services/asset_library/__init__.py
```

```python
# api/services/asset_library/constants.py
"""Asset Library constants — MIME whitelist and asset-type enum."""

from enum import StrEnum


class AssetType(StrEnum):
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
    """Return True if `mime` is permitted for `asset_type`. Prompts always return False."""
    allowed = ALLOWED_MIME_BY_TYPE.get(asset_type)
    return allowed is not None and mime in allowed
```

**Step 4: Run test to verify it passes**

Run: `uv run --project api pytest api/tests/unit_tests/services/asset_library/test_constants.py -v`
Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add api/services/asset_library/__init__.py api/services/asset_library/constants.py api/tests/unit_tests/services/asset_library/test_constants.py
git commit -m "feat(asset-library): add MIME whitelist and AssetType enum"
```

---

### Task 5：Pydantic schemas（含 prompt_variables 校验）

**Files:**
- Create: `api/services/asset_library/schemas.py`
- Test: `api/tests/unit_tests/services/asset_library/test_schemas.py`

**Step 1: Write the failing test**

```python
# api/tests/unit_tests/services/asset_library/test_schemas.py
import pytest
from pydantic import ValidationError

from services.asset_library.schemas import PromptVariable, PromptVariableList


def test_valid_prompt_variable():
    pv = PromptVariable(name="product_name", type="string", default="", description="x")
    assert pv.name == "product_name"


def test_invalid_name_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="bad name!", type="string")


def test_invalid_type_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="x", type="enum")


def test_default_type_mismatch_rejected():
    with pytest.raises(ValidationError):
        PromptVariable(name="age", type="number", default="not-a-number")


def test_default_type_match_ok():
    PromptVariable(name="age", type="number", default=18)


def test_list_validates_each_item():
    PromptVariableList.validate_python(
        [{"name": "a", "type": "string"}, {"name": "b", "type": "number", "default": 1}]
    )


def test_list_rejects_duplicate_names():
    with pytest.raises(ValidationError):
        PromptVariableList.validate_python(
            [{"name": "a", "type": "string"}, {"name": "a", "type": "number"}]
        )
```

**Step 2: Run test to verify it fails**

Run: `uv run --project api pytest api/tests/unit_tests/services/asset_library/test_schemas.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# api/services/asset_library/schemas.py
"""Pydantic v2 schemas for asset-library payloads."""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter, field_validator, model_validator

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_VAR_TYPE = Literal["string", "number", "boolean"]


class PromptVariable(BaseModel):
    """A single variable definition for a prompt asset."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: _VAR_TYPE
    default: Any | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _NAME_RE.match(value):
            raise ValueError("name must match [A-Za-z_][A-Za-z0-9_]{0,63}")
        return value

    @model_validator(mode="after")
    def _validate_default_type(self) -> "PromptVariable":
        if self.default is None:
            return self
        match self.type:
            case "string":
                if not isinstance(self.default, str):
                    raise ValueError("default must be str when type=string")
            case "number":
                if isinstance(self.default, bool) or not isinstance(self.default, (int, float)):
                    raise ValueError("default must be number when type=number")
            case "boolean":
                if not isinstance(self.default, bool):
                    raise ValueError("default must be bool when type=boolean")
        return self


def _validate_unique_names(items: list[PromptVariable]) -> list[PromptVariable]:
    names = [item.name for item in items]
    if len(names) != len(set(names)):
        raise ValueError("prompt_variables names must be unique")
    return items


PromptVariableList = TypeAdapter(list[PromptVariable])
# Note: uniqueness is enforced by callers via `_validate_unique_names` after parsing.
```

> The unique-name test above expects validation at the list level. Wire that by either using a custom `RootModel` with a `model_validator`, or call `_validate_unique_names` from the service layer after parsing. Pick the `RootModel` route to keep validation co-located:

```python
from pydantic import RootModel


class PromptVariableList(RootModel[list[PromptVariable]]):
    @model_validator(mode="after")
    def _unique(self) -> "PromptVariableList":
        names = [pv.name for pv in self.root]
        if len(names) != len(set(names)):
            raise ValueError("prompt_variables names must be unique")
        return self
```

Adjust the test import accordingly: use `PromptVariableList.model_validate([...])` instead of `validate_python`.

**Step 4: Run test to verify it passes**

Run: `uv run --project api pytest api/tests/unit_tests/services/asset_library/test_schemas.py -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add api/services/asset_library/schemas.py api/tests/unit_tests/services/asset_library/test_schemas.py
git commit -m "feat(asset-library): add prompt_variables Pydantic schemas"
```

---

### Task 6：元数据提取（image / audio / video）

**Files:**
- Create: `api/services/asset_library/metadata_extractor.py`
- Test: `api/tests/unit_tests/services/asset_library/test_metadata_extractor.py`
- Modify: `api/pyproject.toml` (add `mutagen`)

**Step 1: Add `mutagen` dependency**

Edit `api/pyproject.toml` and add `"mutagen>=1.47"` to `[project] dependencies`.

Run: `uv sync --project api`
Expected: lockfile updated, mutagen installed.

**Step 2: Write the failing test**

```python
# api/tests/unit_tests/services/asset_library/test_metadata_extractor.py
"""Unit tests for metadata extractor — Pillow / ffprobe / mutagen mocked."""
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from services.asset_library.metadata_extractor import (
    extract_image_metadata,
    extract_audio_metadata,
    extract_video_metadata,
    extract_video_cover,
)


def test_extract_image_metadata_returns_wh():
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (640, 480)).save(buf, format="PNG")
    md = extract_image_metadata(buf.getvalue())
    assert md.width == 640
    assert md.height == 480


@patch("services.asset_library.metadata_extractor.MutagenFile")
def test_extract_audio_metadata(mut):
    f = MagicMock()
    f.info.length = 12.34
    mut.return_value = f
    md = extract_audio_metadata(b"fake")
    assert md.duration == pytest.approx(12.34)


@patch("services.asset_library.metadata_extractor.subprocess.run")
def test_extract_video_metadata(run):
    run.return_value = MagicMock(
        stdout='{"streams":[{"codec_type":"video","width":1920,"height":1080,"duration":"15.2"}]}',
        returncode=0,
    )
    md = extract_video_metadata(b"fake")
    assert md.width == 1920
    assert md.height == 1080
    assert md.duration == pytest.approx(15.2)


@patch("services.asset_library.metadata_extractor.subprocess.run")
def test_extract_video_cover_returns_bytes(run):
    # ffmpeg writes JPEG into the output path; fake by returning code 0
    run.return_value = MagicMock(returncode=0)
    with patch("builtins.open", create=True) as op_:
        op_.return_value.__enter__.return_value.read.return_value = b"jpegbytes"
        cover = extract_video_cover(b"fake-mp4")
    assert cover == b"jpegbytes"


@patch("services.asset_library.metadata_extractor.subprocess.run")
def test_extract_video_metadata_raises_on_failure(run):
    run.return_value = MagicMock(returncode=1, stderr="ffprobe error")
    with pytest.raises(RuntimeError):
        extract_video_metadata(b"fake")
```

**Step 3: Run test to verify it fails**

Run: `uv run --project api pytest api/tests/unit_tests/services/asset_library/test_metadata_extractor.py -v`
Expected: FAIL

**Step 4: Write minimal implementation**

```python
# api/services/asset_library/metadata_extractor.py
"""
Synchronous metadata extraction for asset-library uploads.

External dependencies:
- Pillow (Python) for images
- mutagen (Python) for audio
- ffprobe / ffmpeg (system binaries) for video metadata + cover

All callers are in the asset-library service layer, executed inside the upload
request lifecycle. Expected latency budget: < 2s per call.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional

from mutagen import File as MutagenFile
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageMeta:
    width: int
    height: int


@dataclass(frozen=True)
class AudioMeta:
    duration: Optional[float]


@dataclass(frozen=True)
class VideoMeta:
    width: Optional[int]
    height: Optional[int]
    duration: Optional[float]


def extract_image_metadata(content: bytes) -> ImageMeta:
    with Image.open(BytesIO(content)) as img:
        return ImageMeta(width=img.width, height=img.height)


def extract_audio_metadata(content: bytes) -> AudioMeta:
    with tempfile.NamedTemporaryFile(suffix=".audio") as tmp:
        tmp.write(content)
        tmp.flush()
        f = MutagenFile(tmp.name)
        if f is None or not getattr(f, "info", None):
            return AudioMeta(duration=None)
        return AudioMeta(duration=float(f.info.length))


def extract_video_metadata(content: bytes) -> VideoMeta:
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        tmp.write(content)
        tmp.flush()
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", tmp.name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        data = json.loads(result.stdout or "{}")
        width = height = None
        duration: Optional[float] = None
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                width = s.get("width")
                height = s.get("height")
                d = s.get("duration")
                duration = float(d) if d is not None else duration
                break
        return VideoMeta(width=width, height=height, duration=duration)


def extract_video_cover(content: bytes) -> bytes:
    """Extract a JPEG cover frame at second 1. Returns the JPEG bytes."""
    with tempfile.TemporaryDirectory() as d:
        in_path = Path(d) / "in.mp4"
        out_path = Path(d) / "cover.jpg"
        in_path.write_bytes(content)
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-ss", "1", "-i", str(in_path),
                "-vframes", "1", "-q:v", "2", str(out_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")
        with open(out_path, "rb") as fh:
            return fh.read()
```

**Step 5: Run test to verify it passes**

Run: `uv run --project api pytest api/tests/unit_tests/services/asset_library/test_metadata_extractor.py -v`
Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add api/pyproject.toml api/uv.lock api/services/asset_library/metadata_extractor.py api/tests/unit_tests/services/asset_library/test_metadata_extractor.py
git commit -m "feat(asset-library): add metadata extractor (Pillow/mutagen/ffmpeg)"
```

---

### Task 7：`AssetLibraryService` — 创建提示词

**Files:**
- Create: `api/services/asset_library_service.py`
- Test: `api/tests/unit_tests/services/test_asset_library_service.py`

**Step 1: Write the failing test (prompt creation only)**

```python
# api/tests/unit_tests/services/test_asset_library_service.py
import pytest

from services.asset_library_service import AssetLibraryService
from services.errors.asset_library import InvalidPromptVariablesError


@pytest.mark.unit
def test_create_prompt_asset_persists(asset_library_db_session, fake_account, fake_tenant):
    asset = AssetLibraryService.create_prompt_asset(
        tenant_id=fake_tenant.id,
        user=fake_account,
        name="种草模板",
        content="为 {{product_name}} 写文案",
        prompt_variables=[{"name": "product_name", "type": "string"}],
        description="小红书",
        tags=["种草"],
        category="模板",
    )
    assert asset.id is not None
    assert asset.tenant_id == fake_tenant.id
    assert asset.asset_type == "prompt"
    assert asset.content.startswith("为 {{")
    assert asset.upload_file_id is None


@pytest.mark.unit
def test_create_prompt_asset_invalid_vars_raises(fake_account, fake_tenant):
    with pytest.raises(InvalidPromptVariablesError):
        AssetLibraryService.create_prompt_asset(
            tenant_id=fake_tenant.id,
            user=fake_account,
            name="bad",
            content="x",
            prompt_variables=[{"name": "bad name!", "type": "string"}],
            description=None,
            tags=[],
            category=None,
        )
```

> Add fixtures `asset_library_db_session`, `fake_account`, `fake_tenant` to `api/tests/unit_tests/conftest.py` if not already present. Reuse `api/tests/conftest.py` patterns if such fixtures exist there.

**Step 2: Run test to verify it fails**

Run: `uv run --project api pytest api/tests/unit_tests/services/test_asset_library_service.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'services.asset_library_service'`

**Step 3: Implement minimal**

```python
# api/services/asset_library_service.py
"""
AssetLibraryService — tenant-shared asset management.

All public methods take `tenant_id` as the first argument. Queries are scoped
by `tenant_id` end-to-end; cross-tenant access raises AssetNotFoundError.

File assets reuse the existing `FileService.upload_file` flow and store an
`upload_file_id` reference. Prompt assets store text inline in `content`.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from extensions.ext_database import db
from models import Account
from models.asset_library import AssetLibrary
from services.asset_library.constants import AssetType
from services.asset_library.schemas import PromptVariableList
from services.errors.asset_library import (
    AssetNotFoundError,
    InvalidPromptVariablesError,
)

logger = logging.getLogger(__name__)


class AssetLibraryService:
    """Static-method service. Each method is a self-contained use case."""

    @staticmethod
    def create_prompt_asset(
        *,
        tenant_id: str,
        user: Account,
        name: str,
        content: str,
        prompt_variables: list[dict[str, Any]],
        description: str | None,
        tags: list[str],
        category: str | None,
    ) -> AssetLibrary:
        """Validate and persist a prompt asset. Raises InvalidPromptVariablesError."""
        try:
            parsed = PromptVariableList.model_validate(prompt_variables)
        except ValidationError as exc:
            raise InvalidPromptVariablesError(str(exc)) from exc

        with Session(db.engine, expire_on_commit=False) as session:
            asset = AssetLibrary(
                tenant_id=tenant_id,
                created_by=user.id,
                asset_type=AssetType.PROMPT,
                name=name,
                description=description,
                tags=list(tags),
                category=category,
                content=content,
                prompt_variables=[pv.model_dump() for pv in parsed.root],
            )
            session.add(asset)
            session.commit()
            session.refresh(asset)
            return asset

    @staticmethod
    def get_asset(tenant_id: str, asset_id: str) -> AssetLibrary:
        with Session(db.engine, expire_on_commit=False) as session:
            asset = session.get(AssetLibrary, asset_id)
            if asset is None or asset.tenant_id != tenant_id:
                raise AssetNotFoundError(f"asset {asset_id} not found")
            return asset
```

**Step 4: Run test to verify it passes**

Run: `uv run --project api pytest api/tests/unit_tests/services/test_asset_library_service.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add api/services/asset_library_service.py api/tests/unit_tests/services/test_asset_library_service.py
git commit -m "feat(asset-library): AssetLibraryService.create_prompt_asset + get_asset"
```

---

### Task 8：`AssetLibraryService.create_file_asset`

**Files:**
- Modify: `api/services/asset_library_service.py`
- Modify: `api/tests/unit_tests/services/test_asset_library_service.py`

**Step 1: Write the failing tests**

```python
# Append to test_asset_library_service.py
from io import BytesIO
from unittest.mock import patch, MagicMock

from services.errors.asset_library import UnsupportedMimeTypeError


@pytest.mark.unit
@patch("services.asset_library_service.FileService")
def test_create_file_asset_image_persists(fs_cls, asset_library_db_session, fake_account, fake_tenant):
    fs = fs_cls.return_value
    upload = MagicMock(id="up-id-1", size=1234)
    fs.upload_file.return_value = upload

    asset = AssetLibraryService.create_file_asset(
        tenant_id=fake_tenant.id,
        user=fake_account,
        file_content=BytesIO(b"\x89PNG\r\n").getvalue(),  # actual test should pass real PNG
        filename="x.png",
        mimetype="image/png",
        asset_type=AssetType.IMAGE,
        name="x",
        description=None, tags=[], category=None,
    )
    assert asset.upload_file_id == "up-id-1"
    assert asset.asset_type == "image"


@pytest.mark.unit
def test_create_file_asset_rejects_bad_mime(fake_account, fake_tenant):
    with pytest.raises(UnsupportedMimeTypeError):
        AssetLibraryService.create_file_asset(
            tenant_id=fake_tenant.id,
            user=fake_account,
            file_content=b"xx",
            filename="x.bmp",
            mimetype="image/bmp",
            asset_type=AssetType.IMAGE,
            name="x",
            description=None, tags=[], category=None,
        )
```

> For the happy-path image test, generate a real PNG via Pillow inline so the metadata extractor produces `width`/`height`. Mock `FileService.upload_file` to avoid touching real storage.

**Step 2: Run test to verify it fails**

Run: `uv run --project api pytest api/tests/unit_tests/services/test_asset_library_service.py -v`
Expected: FAIL — method doesn't exist.

**Step 3: Implement**

Add to `AssetLibraryService`:

```python
@staticmethod
def create_file_asset(
    *,
    tenant_id: str,
    user: Account,
    file_content: bytes,
    filename: str,
    mimetype: str,
    asset_type: AssetType,
    name: str,
    description: str | None,
    tags: list[str],
    category: str | None,
) -> AssetLibrary:
    """
    1. MIME whitelist guard
    2. FileService.upload_file -> persists upload_files row + storage object
    3. Extract metadata (width/height/duration) per asset_type
    4. For video: extract cover frame, upload to storage as a sibling, set cover_url
    5. Persist AssetLibrary; on metadata/cover failure, log + continue with NULLs
    """
    if not is_mime_allowed(asset_type, mimetype):
        raise UnsupportedMimeTypeError(mimetype)

    file_service = FileService(db.engine)
    upload = file_service.upload_file(
        filename=filename,
        content=file_content,
        mimetype=mimetype,
        user=user,
    )

    width = height = None
    duration: float | None = None
    cover_url: str | None = None

    try:
        if asset_type is AssetType.IMAGE:
            md = extract_image_metadata(file_content)
            width, height = md.width, md.height
        elif asset_type is AssetType.AUDIO:
            duration = extract_audio_metadata(file_content).duration
        elif asset_type is AssetType.VIDEO:
            md = extract_video_metadata(file_content)
            width, height, duration = md.width, md.height, md.duration
            cover_url = _maybe_upload_video_cover(file_service, file_content, user)
    except Exception:  # noqa: BLE001 — extraction is best-effort
        logger.warning("metadata extraction failed for asset_type=%s", asset_type, exc_info=True)

    with Session(db.engine, expire_on_commit=False) as session:
        asset = AssetLibrary(
            tenant_id=tenant_id,
            created_by=user.id,
            asset_type=asset_type,
            name=name,
            description=description,
            tags=list(tags),
            category=category,
            upload_file_id=upload.id,
            cover_url=cover_url,
            duration=duration,
            width=width,
            height=height,
            file_size=upload.size,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        return asset
```

Add module-level helpers + imports:

```python
from io import BytesIO

from services.asset_library.constants import AssetType, is_mime_allowed
from services.asset_library.metadata_extractor import (
    extract_audio_metadata,
    extract_image_metadata,
    extract_video_cover,
    extract_video_metadata,
)
from services.errors.asset_library import UnsupportedMimeTypeError
from services.file_service import FileService


def _maybe_upload_video_cover(file_service, video_bytes: bytes, user) -> str | None:
    try:
        cover_bytes = extract_video_cover(video_bytes)
    except Exception:
        logger.warning("video cover extraction failed", exc_info=True)
        return None
    cover_upload = file_service.upload_file(
        filename="cover.jpg",
        content=cover_bytes,
        mimetype="image/jpeg",
        user=user,
    )
    # Build a previewable URL via existing helper if available; else return key.
    return f"upload_file_id:{cover_upload.id}"
```

> Confirm `FileService.upload_file` signature in `api/services/file_service.py` (already inspected) and adjust args. Confirm whether a `preview_file_url` helper exists; if so, use it instead of the placeholder string above.

**Step 4: Run tests to verify pass**

Run: `uv run --project api pytest api/tests/unit_tests/services/test_asset_library_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/services/asset_library_service.py api/tests/unit_tests/services/test_asset_library_service.py
git commit -m "feat(asset-library): AssetLibraryService.create_file_asset"
```

---

### Task 9：list / update / delete

**Files:**
- Modify: `api/services/asset_library_service.py`
- Modify: `api/tests/unit_tests/services/test_asset_library_service.py`

**Step 1: Write the failing tests**

```python
@pytest.mark.unit
def test_list_assets_tenant_isolation(asset_library_db_session, fake_account, fake_tenant, other_tenant):
    # Create one asset in fake_tenant + one in other_tenant
    AssetLibraryService.create_prompt_asset(
        tenant_id=fake_tenant.id, user=fake_account, name="A", content="x",
        prompt_variables=[], description=None, tags=[], category=None,
    )
    AssetLibraryService.create_prompt_asset(
        tenant_id=other_tenant.id, user=fake_account, name="B", content="x",
        prompt_variables=[], description=None, tags=[], category=None,
    )
    page = AssetLibraryService.list_assets(tenant_id=fake_tenant.id)
    assert all(a.tenant_id == fake_tenant.id for a in page.items)
    assert page.total == 1


@pytest.mark.unit
def test_update_metadata_whitelist_only(asset_library_db_session, fake_account, fake_tenant):
    asset = AssetLibraryService.create_prompt_asset(
        tenant_id=fake_tenant.id, user=fake_account, name="A", content="x",
        prompt_variables=[], description=None, tags=[], category=None,
    )
    updated = AssetLibraryService.update_asset_metadata(
        tenant_id=fake_tenant.id,
        asset_id=asset.id,
        name="renamed",
        description="new",
        # asset_type/upload_file_id/file_size silently ignored or rejected
    )
    assert updated.name == "renamed"
    assert updated.asset_type == "prompt"  # unchanged


@pytest.mark.unit
def test_delete_prompt_asset(asset_library_db_session, fake_account, fake_tenant):
    asset = AssetLibraryService.create_prompt_asset(
        tenant_id=fake_tenant.id, user=fake_account, name="A", content="x",
        prompt_variables=[], description=None, tags=[], category=None,
    )
    AssetLibraryService.delete_asset(tenant_id=fake_tenant.id, asset_id=asset.id)
    with pytest.raises(AssetNotFoundError):
        AssetLibraryService.get_asset(tenant_id=fake_tenant.id, asset_id=asset.id)


@pytest.mark.unit
def test_delete_cross_tenant_raises(asset_library_db_session, fake_account, fake_tenant, other_tenant):
    asset = AssetLibraryService.create_prompt_asset(
        tenant_id=fake_tenant.id, user=fake_account, name="A", content="x",
        prompt_variables=[], description=None, tags=[], category=None,
    )
    with pytest.raises(AssetNotFoundError):
        AssetLibraryService.delete_asset(tenant_id=other_tenant.id, asset_id=asset.id)
```

**Step 2: Run tests to verify they fail**

Run: `uv run --project api pytest api/tests/unit_tests/services/test_asset_library_service.py -v`
Expected: 4 FAILs

**Step 3: Implement**

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class AssetPage:
    items: list[AssetLibrary]
    total: int
    page: int
    limit: int

    @property
    def has_more(self) -> bool:
        return self.page * self.limit < self.total


_UPDATABLE_FIELDS = frozenset({"name", "description", "tags", "category", "content", "prompt_variables"})


class AssetLibraryService:
    # ... existing methods ...

    @staticmethod
    def list_assets(
        *,
        tenant_id: str,
        asset_type: str | None = None,
        keyword: str | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> AssetPage:
        from sqlalchemy import select, func as sa_func
        with Session(db.engine, expire_on_commit=False) as session:
            stmt = select(AssetLibrary).where(AssetLibrary.tenant_id == tenant_id)
            if asset_type:
                stmt = stmt.where(AssetLibrary.asset_type == asset_type)
            if keyword:
                kw = f"%{keyword}%"
                stmt = stmt.where(
                    AssetLibrary.name.ilike(kw) | AssetLibrary.description.ilike(kw)
                )
            if category:
                stmt = stmt.where(AssetLibrary.category == category)
            if tags:
                # JSONB contains: tags @> '[<tag>]'
                from sqlalchemy.dialects.postgresql import JSONB
                from sqlalchemy import cast
                for t in tags:
                    stmt = stmt.where(AssetLibrary.tags.op("@>")(cast([t], JSONB)))

            count_stmt = select(sa_func.count()).select_from(stmt.subquery())
            total = session.execute(count_stmt).scalar_one()

            stmt = stmt.order_by(AssetLibrary.created_at.desc()).offset((page - 1) * limit).limit(limit)
            items = list(session.execute(stmt).scalars())
            return AssetPage(items=items, total=total, page=page, limit=limit)

    @staticmethod
    def update_asset_metadata(
        *, tenant_id: str, asset_id: str, **fields: Any
    ) -> AssetLibrary:
        with Session(db.engine, expire_on_commit=False) as session:
            asset = session.get(AssetLibrary, asset_id)
            if asset is None or asset.tenant_id != tenant_id:
                raise AssetNotFoundError(f"asset {asset_id} not found")

            for key, value in fields.items():
                if key not in _UPDATABLE_FIELDS or value is None:
                    continue
                if key == "prompt_variables":
                    try:
                        parsed = PromptVariableList.model_validate(value)
                    except ValidationError as exc:
                        raise InvalidPromptVariablesError(str(exc)) from exc
                    setattr(asset, key, [pv.model_dump() for pv in parsed.root])
                else:
                    setattr(asset, key, value)

            session.commit()
            session.refresh(asset)
            return asset

    @staticmethod
    def delete_asset(*, tenant_id: str, asset_id: str) -> None:
        with Session(db.engine, expire_on_commit=False) as session:
            asset = session.get(AssetLibrary, asset_id)
            if asset is None or asset.tenant_id != tenant_id:
                raise AssetNotFoundError(f"asset {asset_id} not found")

            upload_file_id = asset.upload_file_id
            session.delete(asset)
            session.commit()

        if upload_file_id:
            try:
                # Reuse FileService deletion path; if no public method exists,
                # fall back to direct upload_files row + storage cleanup.
                FileService(db.engine).delete_file_by_id(upload_file_id)  # type: ignore[attr-defined]
            except Exception:
                logger.warning("upload_file cleanup failed for %s", upload_file_id, exc_info=True)
```

> Verify the actual `FileService` deletion API exists. If not, perform an inline `session.delete(upload_file)` + `storage.delete(key)` block, mirroring how Dify's existing controllers delete uploads.

**Step 4: Run tests to verify pass**

Run: `uv run --project api pytest api/tests/unit_tests/services/test_asset_library_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/services/asset_library_service.py api/tests/unit_tests/services/test_asset_library_service.py
git commit -m "feat(asset-library): list/update/delete on AssetLibraryService"
```

---

## Phase 3：HTTP 层

### Task 10：响应序列化字段

**Files:**
- Create: `api/fields/asset_library_fields.py`

```python
"""flask_restful field definitions for AssetLibrary serialization."""
from flask_restful import fields

from libs.helper import TimestampField


asset_creator_fields = {
    "id": fields.String,
    "name": fields.String,
    "avatar": fields.String,
}


asset_fields = {
    "id": fields.String,
    "tenant_id": fields.String,
    "asset_type": fields.String,
    "name": fields.String,
    "description": fields.String,
    "tags": fields.Raw,
    "category": fields.String,

    # File-only
    "upload_file_id": fields.String,
    "cover_url": fields.String,
    "signed_url": fields.String,           # populated by service before serializing
    "duration": fields.Float,
    "width": fields.Integer,
    "height": fields.Integer,
    "file_size": fields.Integer,

    # Prompt-only
    "content": fields.String,
    "prompt_variables": fields.Raw,

    "created_by": fields.Nested(asset_creator_fields, allow_null=True),
    "created_at": TimestampField,
    "updated_at": TimestampField,
}


asset_pagination_fields = {
    "data": fields.List(fields.Nested(asset_fields)),
    "total": fields.Integer,
    "page": fields.Integer,
    "limit": fields.Integer,
    "has_more": fields.Boolean,
}
```

> Verify `TimestampField` import path and adjust if needed.

Commit: `feat(asset-library): add response serializer fields`

---

### Task 11：Controllers — `__init__.py` 蓝图 + assets.py（list/get/update/delete）

**Files:**
- Create: `api/controllers/console/asset_library/__init__.py`
- Create: `api/controllers/console/asset_library/assets.py`
- Modify: `api/controllers/console/__init__.py` (register module + add to creator allow-list)

```python
# api/controllers/console/asset_library/__init__.py
"""Asset Library controllers — files, prompts, generic CRUD."""
```

```python
# api/controllers/console/asset_library/assets.py
"""GET list / GET detail / PATCH update / DELETE."""
from flask import request
from flask_restful import Resource, marshal_with, reqparse

from controllers.console import api
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
)
from fields.asset_library_fields import asset_fields, asset_pagination_fields
from libs.login import login_required
from services.asset_library_service import AssetLibraryService
from services.errors.asset_library import (
    AssetNotFoundError,
    InvalidPromptVariablesError,
)
from werkzeug.exceptions import BadRequest, NotFound


class AssetListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(asset_pagination_fields)
    def get(self):
        from flask_login import current_user
        parser = reqparse.RequestParser()
        parser.add_argument("type", type=str, required=False, location="args")
        parser.add_argument("keyword", type=str, required=False, location="args")
        parser.add_argument("category", type=str, required=False, location="args")
        parser.add_argument("tags", type=str, action="append", required=False, location="args")
        parser.add_argument("page", type=int, default=1, location="args")
        parser.add_argument("limit", type=int, default=20, location="args")
        args = parser.parse_args()

        page = AssetLibraryService.list_assets(
            tenant_id=current_user.current_tenant_id,
            asset_type=args["type"],
            keyword=args["keyword"],
            tags=args["tags"],
            category=args["category"],
            page=args["page"],
            limit=min(args["limit"], 100),
        )
        return {
            "data": page.items,
            "total": page.total,
            "page": page.page,
            "limit": page.limit,
            "has_more": page.has_more,
        }


class AssetDetailApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(asset_fields)
    def get(self, asset_id: str):
        from flask_login import current_user
        try:
            return AssetLibraryService.get_asset(current_user.current_tenant_id, asset_id)
        except AssetNotFoundError as exc:
            raise NotFound(str(exc)) from exc

    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(asset_fields)
    def patch(self, asset_id: str):
        from flask_login import current_user
        body = request.get_json(silent=True) or {}
        try:
            return AssetLibraryService.update_asset_metadata(
                tenant_id=current_user.current_tenant_id,
                asset_id=asset_id,
                **body,
            )
        except AssetNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except InvalidPromptVariablesError as exc:
            raise BadRequest(str(exc)) from exc

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, asset_id: str):
        from flask_login import current_user
        try:
            AssetLibraryService.delete_asset(
                tenant_id=current_user.current_tenant_id, asset_id=asset_id
            )
        except AssetNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        return "", 204


api.add_resource(AssetListApi, "/asset-library")
api.add_resource(AssetDetailApi, "/asset-library/<string:asset_id>")
```

In `api/controllers/console/__init__.py`:
- Add `"/console/api/asset-library"` to `_CREATOR_ALLOWED_PREFIXES`.
- Add `from .asset_library import assets as asset_library_assets` to the import block.

**Test:** `api/tests/unit_tests/controllers/console/asset_library/test_assets_controller.py` — covers 401 (no auth), 404 (cross-tenant), 200 list, 200 detail, 200 patch, 204 delete. Use Dify's existing controller test fixtures (mock `current_user`, mock service layer).

Commit: `feat(asset-library): list/detail/update/delete controllers`

---

### Task 12：Controllers — files.py（创建文件类素材）

**Files:**
- Create: `api/controllers/console/asset_library/files.py`
- Modify: `api/controllers/console/__init__.py`

```python
# api/controllers/console/asset_library/files.py
"""POST /asset-library/files — multipart upload for image/audio/video."""
import json
import logging

from flask import request
from flask_login import current_user
from flask_restful import Resource, marshal_with
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from controllers.console import api
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
)
from fields.asset_library_fields import asset_fields
from libs.login import login_required
from services.asset_library.constants import AssetType
from services.asset_library_service import AssetLibraryService
from services.errors.asset_library import (
    FileSizeLimitExceededError,
    UnsupportedMimeTypeError,
)
from services.errors.file import FileTooLargeError, UnsupportedFileTypeError

logger = logging.getLogger(__name__)


class AssetFileUploadApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(asset_fields)
    def post(self):
        if "file" not in request.files:
            raise BadRequest("file part is required")
        file = request.files["file"]

        try:
            asset_type = AssetType(request.form.get("asset_type", ""))
        except ValueError as exc:
            raise BadRequest("asset_type must be image | audio | video") from exc

        name = request.form.get("name") or file.filename or "untitled"
        description = request.form.get("description")
        category = request.form.get("category")
        tags_raw = request.form.get("tags") or "[]"
        try:
            tags = list(json.loads(tags_raw))
        except (TypeError, ValueError) as exc:
            raise BadRequest("tags must be a JSON array of strings") from exc

        content = file.read()

        try:
            asset = AssetLibraryService.create_file_asset(
                tenant_id=current_user.current_tenant_id,
                user=current_user,
                file_content=content,
                filename=file.filename or "untitled",
                mimetype=file.mimetype,
                asset_type=asset_type,
                name=name,
                description=description,
                tags=tags,
                category=category,
            )
        except UnsupportedMimeTypeError as exc:
            raise BadRequest(str(exc)) from exc
        except UnsupportedFileTypeError as exc:
            raise BadRequest("unsupported file type") from exc
        except (FileSizeLimitExceededError, FileTooLargeError) as exc:
            raise RequestEntityTooLarge(str(exc)) from exc

        return asset, 201


api.add_resource(AssetFileUploadApi, "/asset-library/files")
```

Wire import in `controllers/console/__init__.py`:
```python
from .asset_library import files as asset_library_files
```

Tests: `test_files_controller.py` covers 201 happy path (mocked service), 400 bad mime, 400 bad asset_type, 413 too large, 401.

Commit: `feat(asset-library): file upload controller`

---

### Task 13：Controllers — prompts.py

**Files:**
- Create: `api/controllers/console/asset_library/prompts.py`
- Modify: `api/controllers/console/__init__.py`

```python
# api/controllers/console/asset_library/prompts.py
"""POST /asset-library/prompts — JSON create for prompt assets."""
from flask import request
from flask_login import current_user
from flask_restful import Resource, marshal_with
from werkzeug.exceptions import BadRequest

from controllers.console import api
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
)
from fields.asset_library_fields import asset_fields
from libs.login import login_required
from services.asset_library_service import AssetLibraryService
from services.errors.asset_library import InvalidPromptVariablesError


class AssetPromptCreateApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @marshal_with(asset_fields)
    def post(self):
        body = request.get_json(silent=True) or {}
        name = body.get("name")
        content = body.get("content")
        if not name or not content:
            raise BadRequest("name and content are required")

        try:
            asset = AssetLibraryService.create_prompt_asset(
                tenant_id=current_user.current_tenant_id,
                user=current_user,
                name=name,
                content=content,
                prompt_variables=body.get("prompt_variables", []),
                description=body.get("description"),
                tags=body.get("tags", []),
                category=body.get("category"),
            )
        except InvalidPromptVariablesError as exc:
            raise BadRequest(str(exc)) from exc
        return asset, 201


api.add_resource(AssetPromptCreateApi, "/asset-library/prompts")
```

Wire import in `controllers/console/__init__.py`. Tests: 201 happy path + 400 invalid vars + 400 missing fields + 401.

Commit: `feat(asset-library): prompt creation controller`

---

## Phase 4：后端验收

### Task 14：跑全套 service + controller 单测

Run: `uv run --project api pytest api/tests/unit_tests/services/asset_library api/tests/unit_tests/services/test_asset_library_service.py api/tests/unit_tests/controllers/console/asset_library api/tests/unit_tests/services/errors/test_asset_library_errors.py api/tests/unit_tests/models/test_asset_library.py -v`
Expected: ALL PASS, > 80% coverage on `services/asset_library_service.py` + `services/asset_library/*`.

### Task 15：项目级 lint + type-check

Run from `/Users/guijinhao/Documents/zhongda/dify`:
```bash
cd api && make lint && make type-check
```
Expected: zero errors. Fix any new findings; do **not** add `# type: ignore` blindly.

### Task 16：手测 happy path（curl）

Start the API stack as the user normally does (do not start servers from agent context — instruct user instead). Once it's running, suggest the user try:

```bash
# Login first to obtain a console JWT (out of scope here).
TOKEN=...

# Create prompt
curl -X POST http://localhost:5001/console/api/asset-library/prompts \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"种草","content":"x","prompt_variables":[{"name":"a","type":"string"}]}'

# Upload image
curl -X POST http://localhost:5001/console/api/asset-library/files \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/test.png" \
  -F "asset_type=image" -F "name=测试图"

# List
curl "http://localhost:5001/console/api/asset-library?type=image&page=1" \
  -H "Authorization: Bearer $TOKEN"
```

Verify each response shape matches the design doc.

### Task 17：最终提交 + 文档更新

If any docstrings drifted vs design, update `docs/plans/2026-04-28-asset-library-design.md` notes section. Commit with `docs(asset-library): finalize backend notes` if any.

**Stop here. Phase 5 (frontend) is a separate brainstorm session, not part of this plan.**

---

## 风险与回滚

- **迁移失败**：`uv run --project api flask db downgrade` 回滚一格。
- **mutagen 安装失败**：检查 `uv.lock`，必要时锁定版本。
- **ffmpeg 未装**：service 层已经把元数据提取放在 try/except，不会阻塞素材入库（cover_url/duration 留 NULL）。
- **跨租户泄漏**：每个 service 方法首参强制 `tenant_id`，且每条用例都有 cross-tenant 测试。

## YAGNI 提醒

不要在这个计划范围里做：
- ❌ 提示词版本管理 / 历史回滚
- ❌ 提示词被 workflow 节点直接引用
- ❌ 上传人级权限（只展示 `created_by`）
- ❌ 异步抽帧（同步即可，慢了再迁 Celery）
- ❌ 前端实现（单独 brainstorm）
