"""Synchronous metadata extraction for asset-library uploads.

Called from ``AssetLibraryService.create_file_asset`` inside the upload
request lifecycle. Latency budget: < 2s per call.

External dependencies:
- Pillow (Python) for image dimensions
- mutagen (Python) for audio duration
- ffprobe / ffmpeg (system binaries) for video metadata + cover frame

The video extractor writes the input bytes to a temp file before calling
ffprobe/ffmpeg because both binaries operate on file paths, not stdin.
Audio extraction does the same because mutagen needs a path to sniff
container format.

All functions raise ``RuntimeError`` for hard failures. The service layer
treats these as best-effort and persists ``NULL`` rather than aborting the
upload — see ``AssetLibraryService.create_file_asset``.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from mutagen._file import File as MutagenFile
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageMeta:
    """Width/height read from an image's bytes."""

    width: int
    height: int


@dataclass(frozen=True)
class AudioMeta:
    """Duration in seconds; ``None`` when mutagen cannot identify the format."""

    duration: float | None


@dataclass(frozen=True)
class VideoMeta:
    """Width/height/duration from ffprobe; any field may be ``None``."""

    width: int | None
    height: int | None
    duration: float | None


def extract_image_metadata(content: bytes) -> ImageMeta:
    """Read width/height from in-memory image bytes via Pillow."""
    with Image.open(BytesIO(content)) as img:
        return ImageMeta(width=img.width, height=img.height)


def extract_audio_metadata(content: bytes) -> AudioMeta:
    """Read duration from audio bytes via mutagen.

    mutagen needs a path; bytes are written to a tempfile then sniffed.
    Returns ``AudioMeta(duration=None)`` if mutagen cannot identify the
    container — never raises for unparseable input.
    """
    with tempfile.NamedTemporaryFile(suffix=".audio") as tmp:
        tmp.write(content)
        tmp.flush()
        muta = MutagenFile(tmp.name)
        if muta is None:
            return AudioMeta(duration=None)
        info = getattr(muta, "info", None)
        length = getattr(info, "length", None) if info is not None else None
        if length is None:
            return AudioMeta(duration=None)
        return AudioMeta(duration=float(length))


def extract_video_metadata(content: bytes) -> VideoMeta:
    """Read width/height/duration from video bytes via ffprobe.

    Raises ``RuntimeError`` when ffprobe exits non-zero. Returns
    ``VideoMeta`` with all fields ``None`` if ffprobe succeeded but no
    video stream was reported.
    """
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        tmp.write(content)
        tmp.flush()
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                tmp.name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        data = json.loads(result.stdout or "{}")
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width")
                height = stream.get("height")
                duration_raw = stream.get("duration")
                duration = float(duration_raw) if duration_raw is not None else None
                return VideoMeta(width=width, height=height, duration=duration)
    return VideoMeta(width=None, height=None, duration=None)


def extract_video_cover(content: bytes) -> bytes:
    """Extract a JPEG cover frame at second 1 via ffmpeg.

    Returns the JPEG bytes. Raises ``RuntimeError`` on ffmpeg failure.
    """
    with tempfile.TemporaryDirectory() as work_dir:
        in_path = Path(work_dir) / "in.mp4"
        out_path = Path(work_dir) / "cover.jpg"
        in_path.write_bytes(content)

        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "1",
                "-i",
                str(in_path),
                "-vframes",
                "1",
                "-q:v",
                "2",
                str(out_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr}")
        return out_path.read_bytes()
