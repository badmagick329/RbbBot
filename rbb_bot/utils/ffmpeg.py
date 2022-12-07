import asyncio
import logging
import sys
from pathlib import Path

from rbb_bot.utils.exceptions import FFmpegError, TimeoutError
from rbb_bot.utils.helpers import subprocess_run


class FFmpeg:
    def __init__(self, logger=None):
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.DEBUG)
            handler = logging.StreamHandler(stream=sys.stdout)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            self.logger.addHandler(handler)

    async def get_duration(self, file_path: str | Path) -> float:
        duration_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=duration",
            "-of",
            "default=nw=1:nk=1",
            str(file_path),
        ]
        self.logger.debug(f"Running command: {' '.join(duration_cmd)}")
        return_code, stdout, stderr = await subprocess_run(duration_cmd)
        if return_code != 0:
            raise FFmpegError(f"Error getting duration: {stderr}")
        return float(stdout)

    async def compress(
        self,
        file_path: str | Path,
        output_path: str | Path,
        file_size: int,
        timeout: int = 20,
    ) -> Path:
        """
        Compresses a video file to a given file size in KB (bytes, not bits)

        Parameters
        ----------
        file_path : str
            The path to the file to compress
        output_path : str
            The path to save the compressed file to
        file_size : int
            The file size in KB to compress the file to
        """
        file_path = str(file_path)
        output_path = str(output_path)
        duration = await self.get_duration(file_path)
        video_bitrate = int((file_size / duration) * 8 * 0.85)
        audio_bitrate = int((file_size / duration) * 8 * 0.06)

        compress_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            file_path,
            "-c:v",
            "libx264",
            "-b:v",
            f"{video_bitrate}k",
            "-c:a",
            "aac",
            "-b:a",
            f"{audio_bitrate}k",
            output_path,
        ]

        self.logger.debug(f"Running command: {' '.join(compress_cmd)}")
        return_code, stdout, stderr = await subprocess_run(
            compress_cmd, timeout=timeout
        )
        self.logger.debug(f"New file size is {Path(output_path).stat().st_size}")

        if return_code != 0:
            raise FFmpegError(f"Error compressing file: {stderr}")
        return Path(output_path)
