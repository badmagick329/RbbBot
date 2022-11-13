import asyncio
import re
from asyncio import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, unquote_plus

import pendulum
from aiohttp import ClientSession
from discord import TextChannel
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
    return Path(unquote_plus(urlparse(url).path)).name


def truncate(string: str, max_length: int = DISCORD_MAX_MESSAGE) -> str:
    """Truncates a string to a max length"""
    return f"{string[: max_length - 4]} ..." if len(string) > max_length else string


def chunker(seq: Iterable, size: int):
    return (seq[pos : pos + size] for pos in range(0, len(seq), size))


async def large_send(channel: TextChannel, msg: str):
    """Sends a message to a channel, splitting it up if it's too long"""
    if len(msg) > DISCORD_MAX_MESSAGE:
        for chunk in chunker(msg, DISCORD_MAX_MESSAGE):
            await channel.send(chunk)
    else:
        await channel.send(msg)


async def http_get(
    web_client: ClientSession,
    url: str,
    timeout: float = 5.0,
    as_text=False,
    as_json=False,
) -> bytes | str:
    async def _get(u):
        async with web_client.get(u) as resp:
            if resp.status != 200:
                raise NotOk(resp.status)
            if as_text:
                return await resp.text()
            if as_json:
                return await resp.json()
            return await resp.read()

    try:
        return await asyncio.wait_for(_get(url), timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError


async def subprocess_run(cmd) -> tuple[int | None, str, str]:
    """
    Runs a subprocess asynchronously and returns the returncode, stdout, and stderr.
    """
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode(), stderr.decode()
