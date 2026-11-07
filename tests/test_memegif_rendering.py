import asyncio
import shutil
import tempfile
import time

import pytest
from PIL import Image

from rbb_bot.memegifs.ffmpeg import (
    FFmpegError,
    _run_ffmpeg,
    concat_clips,
    create_image_clip,
    write_concat_list,
)
from rbb_bot.memegifs.memegen import IreneTweeting

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="FFmpeg is not installed"
)


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    root = tmp_path / "temp-root"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


@pytest.mark.asyncio
async def test_concurrent_renders_return_distinct_gifs_and_clean_up(temp_root):
    first, second = await asyncio.gather(
        IreneTweeting().create("FIRST MEME"),
        IreneTweeting().create("SECOND MEME"),
    )

    assert first.startswith(b"GIF8")
    assert second.startswith(b"GIF8")
    assert first != second
    assert list(temp_root.iterdir()) == []


@pytest.mark.asyncio
async def test_ffmpeg_failure_raises_and_removes_temp_dir(tmp_path, temp_root):
    not_a_video = tmp_path / "not-a-video.mp4"
    not_a_video.write_text("this is not a video", encoding="utf-8")
    meme = IreneTweeting()
    meme.video_file = not_a_video

    with pytest.raises(FFmpegError):
        await meme.create("BROKEN")

    assert list(temp_root.glob("rbb-meme-*")) == []


@pytest.mark.asyncio
async def test_runner_kills_ffmpeg_after_timeout():
    started = time.monotonic()

    with pytest.raises(FFmpegError, match="timed out"):
        await _run_ffmpeg(
            ["-re", "-f", "lavfi", "-i", "nullsrc", "-t", "600", "-f", "null", "-"],
            timeout=0.5,
        )

    assert time.monotonic() - started < 10


@pytest.mark.asyncio
async def test_concat_handles_clip_path_with_single_quote(tmp_path):
    clip_dir = tmp_path / "it's a clip"
    clip_dir.mkdir()
    frame = clip_dir / "frame.png"
    Image.new("RGB", (64, 48), (200, 50, 50)).save(frame)
    clip = clip_dir / "clip.mp4"
    await create_image_clip(frame, clip, 1, 64, 48)
    list_file = clip_dir / "list.txt"
    output = clip_dir / "out.gif"

    write_concat_list([clip], list_file)
    assert list_file.read_text(encoding="utf-8").startswith(
        "file '" + str(clip_dir).replace("'", "'\\''")
    )

    await concat_clips([clip, clip], list_file, output, 64, 48)

    assert output.read_bytes().startswith(b"GIF8")
