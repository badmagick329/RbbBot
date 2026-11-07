import asyncio
from asyncio.subprocess import DEVNULL, PIPE
from pathlib import Path

STDERR_TAIL_CHARS = 500


class FFmpegError(Exception):
    pass


async def _run_ffmpeg(args: list[str], timeout: float = 30.0) -> None:
    """Run FFmpeg with an argument list and fail loudly.

    Arguments go to exec directly, so user-influenced paths never pass through a
    shell. The timeout bounds a hung or runaway encode so a command cannot pin a
    worker; the process is killed and reaped before raising so no zombie is left.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args, stdin=DEVNULL, stdout=DEVNULL, stderr=PIPE
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise FFmpegError(f"ffmpeg timed out after {timeout}s") from None
    if proc.returncode != 0:
        tail = stderr.decode(errors="replace").strip()[-STDERR_TAIL_CHARS:]
        raise FFmpegError(f"ffmpeg exited with code {proc.returncode}: {tail}")


async def create_image_clip(
    image: Path, output: Path, seconds: int, w: int, h: int
) -> None:
    await _run_ffmpeg(
        [
            "-y",
            "-loglevel", "error",
            "-loop", "1",
            "-i", str(image),
            "-c:v", "libx264",
            "-t", str(seconds),
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={w}:{h}",
            str(output),
        ]
    )  # fmt: skip


async def concat_clips(
    clips: list[Path], list_file: Path, output: Path, w: int, h: int
) -> None:
    """Concatenate clips into a single palette-optimised GIF at `output`."""
    write_concat_list(clips, list_file)
    await _run_ffmpeg(
        [
            "-y",
            "-loglevel", "error",
            "-analyzeduration", "2147483647",
            "-probesize", "2147483647",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-filter_complex",
            f"[0:v] scale={w}:{h} [a];[a] split [b][c];[b] palettegen [p];[c][p] paletteuse",
            str(output),
        ]
    )  # fmt: skip


def write_concat_list(clips: list[Path], list_file: Path) -> None:
    """Write an FFmpeg concat-demuxer list for `clips`.

    Inside single quotes the concat syntax has no escapes, so a literal quote is
    written as close-quote, backslash-quote, reopen-quote.
    """
    lines = [_quote_concat_path(clip) for clip in clips]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _quote_concat_path(path: Path) -> str:
    return "file '" + str(path).replace("'", "'\\''") + "'"
