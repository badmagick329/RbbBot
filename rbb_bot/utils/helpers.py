import asyncio
import re
from asyncio import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote_plus, urlparse

import discord
import pendulum
from discord.ext import commands

from rbb_bot.settings.const import DISCORD_MAX_MESSAGE
from rbb_bot.utils.exceptions import NotOk, TimeoutError

emoji_regex = re.compile(r"<(a?):(\w+):(\d+)>")
user_regex = re.compile(r"<@!?(\d+)>")
channel_regex = re.compile(r"<#(\d+)>")
role_regex = re.compile(r"<@&(\d+)>")


async def _call_help(ctx):
    """Shows help for this group."""
    await ctx.send_help(ctx.command.parent)


def auto_help(func):
    if not isinstance(func, commands.Group):
        raise TypeError(f"bad deco order. received func type: {type(func)}")
    cmd = commands.Command(_call_help, name="help", hidden=True)
    func.add_command(cmd)
    return func


def discord_format_time(dt: datetime | pendulum.DateTime | int, relative=False) -> str:
    """Returns a string formatted for discord"""
    timestamp = dt if isinstance(dt, int) else int(dt.timestamp())
    style = "R" if relative else "f"
    return f"<t:{timestamp}:{style}>"


def emoji_url(emoji_id: int, animated: bool) -> str:
    """Returns a url for an emoji"""
    suffix = "gif" if animated else "png"
    return f"https://cdn.discordapp.com/emojis/{emoji_id}.{suffix}"


def url_to_filename(url: str) -> str:
    """Returns a filename from a url"""
    twt_re = r"https?://pbs\.twimg\.com/media/([^?]+)\?format=(\w+)"
    match = re.match(twt_re, url)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    return Path(unquote_plus(urlparse(url).path)).name


def truncate(string: str, max_length: int = DISCORD_MAX_MESSAGE) -> str:
    """Truncates a string to a max length"""
    return f"{string[: max_length - 4]} ..." if len(string) > max_length else string


def chunker(seq: Iterable, size: int, max_len_per_chunk: int = None) -> Iterable:
    chunk = []
    chunk_len = 0
    for item in seq:
        if max_len_per_chunk and chunk_len + len(str(item)) > max_len_per_chunk:
            if not chunk:
                raise ValueError("max_len_per_chunk is too small")
            yield chunk
            chunk = []
            chunk_len = 0
        chunk.append(item)
        chunk_len += len(str(item))
        if len(chunk) == size:
            yield chunk
            chunk = []
            chunk_len = 0
    if chunk:
        yield chunk


_CODE_FENCE_OPEN = "```\n"
_CODE_FENCE_CLOSE = "\n```"


async def large_send(
    channel: discord.TextChannel | discord.DMChannel,
    msg: str,
    *,
    code_block: bool = False,
):
    """Send text of any length as consecutive messages Discord will accept.

    Discord rejects a message over DISCORD_MAX_MESSAGE outright, so an unsplit
    long traceback would be lost rather than truncated. With `code_block`, each
    part gets its own fence, counted against the limit: a fence wrapped around
    the whole text would be cut apart and only the first part would render as
    a code block.
    """
    fence = len(_CODE_FENCE_OPEN) + len(_CODE_FENCE_CLOSE) if code_block else 0
    size = DISCORD_MAX_MESSAGE - fence
    for start in range(0, len(msg), size):
        part = msg[start : start + size]
        if code_block:
            part = f"{_CODE_FENCE_OPEN}{part}{_CODE_FENCE_CLOSE}"
        await channel.send(part)


async def http_get(url: str, timeout: float = 5.0, as_text=False, as_json=False):
    from rbb_bot.infrastructure.http.public_download import download

    try:
        # Bound the whole redirect chain, not just each individual request.
        return await asyncio.wait_for(
            download(url, timeout=timeout, as_text=as_text, as_json=as_json),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise TimeoutError


async def subprocess_run(
    cmd: list[str], timeout: int = 10
) -> tuple[int | None, str, str]:
    """
    Runs a subprocess asynchronously and returns the returncode, stdout, and stderr.
    """
    prog = cmd.pop(0)
    args = cmd
    proc = await asyncio.create_subprocess_exec(
        prog, *args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    async def _wait() -> tuple[str, str]:
        out, err = await proc.communicate()
        return out.decode(), err.decode()

    try:
        stdout, stderr = await asyncio.wait_for(_wait(), timeout=timeout)
        return proc.returncode, stdout, stderr
    except asyncio.TimeoutError:
        proc.kill()
        raise TimeoutError
    finally:
        proc._transport.close()
