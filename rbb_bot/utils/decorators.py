from functools import wraps
from typing import Callable
from copy import deepcopy

from discord.ext.commands import Cog, Context
from tortoise import Tortoise

from rbb_bot.models import CommandLog
from rbb_bot.settings.config import get_creds

DB_URL = get_creds().db_url


def log_command(command_name: str = None) -> Callable:
    def dec(func: Callable) -> Callable:
        @wraps(func)
        async def wrapped(cog: Cog, ctx: Context, *args, **kwargs):
            try:
                await Tortoise.init(
                    db_url=DB_URL, modules={"models": ["rbb_bot.models"]}
                )
                author_id = ctx.author.id
                cmd_name = command_name or ctx.command.qualified_name
                guild_id = ctx.guild.id if ctx.guild else None
                channel_id = ctx.channel.id
                message_id = ctx.message.id
                args_ = args
                kwargs_ = deepcopy(kwargs)
                prefix = ctx.prefix
                await CommandLog.create(
                    command_name=cmd_name,
                    author_id=author_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    message_id=message_id,
                    prefix=prefix or "Not Found",
                    args=[str(a) for a in args_] or None,
                    kwargs={k: str(v) for k, v in kwargs_.items()} or None,
                )
                if ctx.message.attachments:
                    kwargs_.setdefault("attachments", [])
                    for attachment in ctx.message.attachments:
                        kwargs_["attachments"].append(attachment.url)

            except Exception as e:
                CommandLog.client.logger.error(
                    f"Error while logging command [{func.__name__}]:\n{e}"
                )

            await func(cog, ctx, *args, **kwargs)

        return wrapped

    return dec
