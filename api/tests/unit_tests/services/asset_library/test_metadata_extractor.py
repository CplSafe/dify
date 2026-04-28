"""Unit tests for metadata extractor.

External binaries (ffprobe/ffmpeg) and external libs (Pillow, mutagen) are
real for image happy-paths but mocked for audio/video to keep tests
deterministic and not require actual media samples.
"""

import pathlib
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from services.asset_library.metadata_extractor import (
    AudioMeta,
    ImageMeta,
    VideoMeta,
    extract_audio_metadata,
    extract_image_metadata,
    extract_video_cover,
    extract_video_metadata,
)


def test_extract_image_metadata_returns_dimensions():
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (640, 480)).save(buf, format="PNG")
    md = extract_image_metadata(buf.getvalue())

    assert isinstance(md, ImageMeta)
    assert md.width == 640
    assert md.height == 480


@patch("services.asset_library.metadata_extractor.MutagenFile")
def test_extract_audio_metadata_uses_mutagen(mut):
    fake = MagicMock()
    fake.info.length = 12.34
    mut.return_value = fake

    md = extract_audio_metadata(b"fake-audio-bytes")

    assert isinstance(md, AudioMeta)
    assert md.duration == pytest.approx(12.34)


@patch("services.asset_library.metadata_extractor.MutagenFile")
def test_extract_audio_metadata_returns_none_when_unparseable(mut):
    mut.return_value = None

    md = extract_audio_metadata(b"garbage")

    assert md.duration is None


@patch("services.asset_library.metadata_extractor.subprocess.run")
def test_extract_video_metadata_parses_ffprobe(run):
    run.return_value = MagicMock(
        stdout='{"streams":[{"codec_type":"video","width":1920,"height":1080,"duration":"15.2"}]}',
        returncode=0,
        stderr="",
    )

    md = extract_video_metadata(b"fake-mp4")

    assert isinstance(md, VideoMeta)
    assert md.width == 1920
    assert md.height == 1080
    assert md.duration == pytest.approx(15.2)


@patch("services.asset_library.metadata_extractor.subprocess.run")
def test_extract_video_metadata_handles_missing_video_stream(run):
    run.return_value = MagicMock(
        stdout='{"streams":[{"codec_type":"audio","duration":"5.0"}]}',
        returncode=0,
        stderr="",
    )

    md = extract_video_metadata(b"fake-mp4")

    assert md.width is None
    assert md.height is None
    assert md.duration is None


@patch("services.asset_library.metadata_extractor.subprocess.run")
def test_extract_video_metadata_raises_on_ffprobe_failure(run):
    run.return_value = MagicMock(returncode=1, stdout="", stderr="ffprobe error")

    with pytest.raises(RuntimeError):
        extract_video_metadata(b"fake-mp4")


@patch("services.asset_library.metadata_extractor.subprocess.run")
def test_extract_video_cover_returns_jpeg_bytes(run, tmp_path, monkeypatch):
    # ffmpeg writes the JPEG to the output path; simulate that.
    def _fake_run(cmd, *args, **kwargs):
        # cmd is the ffmpeg arg list. Find the output path (last positional).
        out = cmd[-1]
        pathlib.Path(out).write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
        return MagicMock(returncode=0, stdout="", stderr="")

    run.side_effect = _fake_run
    cover = extract_video_cover(b"fake-mp4")
    assert cover.startswith(b"\xff\xd8")  # JPEG magic


@patch("services.asset_library.metadata_extractor.subprocess.run")
def test_extract_video_cover_raises_on_ffmpeg_failure(run):
    run.return_value = MagicMock(returncode=1, stdout="", stderr="ffmpeg failed")

    with pytest.raises(RuntimeError):
        extract_video_cover(b"fake-mp4")
