import asyncio
from pathlib import Path
from typing import Literal


async def create_image_clip(
    input_image: str, output_video: str, time: int, w: int, h: int
) -> int:
    ffmpeg_cmd = (
        'ffmpeg -loop 1 -i "{image}" -c:v libx264 -t {time}'
        ' -pix_fmt yuv420p -vf scale={w}:{h} -loglevel warning "{output}"'
    )
    cmd = ffmpeg_cmd.format(
        image=input_image, time=time, w=w, h=h, output=output_video
    )
    process = await asyncio.create_subprocess_shell(cmd)
    return await process.wait()


async def concat_clips(
    clips: list[str],
    list_file: str,
    concout_name: str,
    w: int,
    h: int,
    suffix: Literal["mp4", "gif"] = "gif",
) -> str:
    """
    Take a list of clips (absolute paths) and concatenate them into a single file
    """
    if any([not Path(c).exists() for c in clips]):
        raise FileNotFoundError("One or more clips do not exist")

    create_list_file(clips, list_file)
    ffmpeg_cmd, concout_name = create_concat_cmd(
        list_file, concout_name, w, h, suffix
    )
    process = await asyncio.create_subprocess_shell(ffmpeg_cmd)
    await process.wait()

    try:
        Path(list_file).unlink(missing_ok=True)
    except Exception:
        pass
    return concout_name


def create_list_file(clips: list[str], list_file: str):
    write_str = "\n".join([f"file '{c}'" for c in clips])
    with open(list_file, "w", encoding="utf-8") as f:
        f.write(write_str)


def create_concat_cmd(
    list_file: str,
    concout_name: str,
    w: int,
    h: int,
    suffix: Literal["mp4", "gif"] = "gif",
) -> tuple[str, str]:
    if suffix == "mp4":
        concat_str = (
            "ffmpeg -analyzeduration 2147483647 -probesize 2147483647"
            " -y -f concat -safe 0 -i {list_file} -c copy"
            ' -loglevel warning "{concout_name}"'
        )
        concout_name = concout_name + ".mp4"
    else:
        concat_str = (
            "ffmpeg -analyzeduration 2147483647 -probesize 2147483647 -y"
            ' -f concat -safe 0 -i {list_file} -filter_complex "[0:v] scale={w}:{h}'
            ' [a];[a] split [b][c];[b] palettegen [p];[c][p] paletteuse"'
            ' -loglevel warning "{concout_name}"'
        )
        concout_name = concout_name + ".gif"
    ffmpeg_cmd = concat_str.format(
        list_file=list_file, w=w, h=h, concout_name=concout_name
    )
    return ffmpeg_cmd, concout_name
