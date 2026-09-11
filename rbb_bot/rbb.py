import asyncio
import logging
from pathlib import Path

import discord
from discord import Activity, ActivityType, Message
from discord.ext import commands
from discord.ext.commands import Context
from rbb_bot.lib.discord_log_handler import DiscordLogHandler
from rbb_bot.models import Guild
from tortoise import Tortoise
from rbb_bot.utils.help_command import EmbedHelpCommand
from rbb_bot.utils.views import ConfirmView

from rbb_bot.settings.config import Config, Creds
from rbb_bot.settings.config import get_discord_settings
from rbb_bot.utils.error_logging import format_error_context
from rbb_bot.utils.mixins import ClientMixin


class RbbBot(commands.Bot):
    def __init__(
        self, config: Config, creds: Creds, logger, web_client, *args, **kwargs
    ):
        self.config = config
        self.discord_settings = get_discord_settings()
        self.creds = creds
        self.logger = logger
        self.web_client = web_client
        self.load_cogs = [
            c.stem
            for c in (Path(__file__).parent / "cogs").glob("*.py")
            if not c.stem.startswith("_")
        ]
        self.guild_prefixes = dict()
        self.logging_task = None
        self._shutdown_task = None
        self.logging_ready = asyncio.Event()
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.emojis_and_stickers = True
        allowed_mentions = discord.AllowedMentions(
            everyone=False, roles=False, users=True
        )

        super().__init__(
            command_prefix=self.retrieve_prefix,
            intents=intents,
            allowed_mentions=allowed_mentions,
            case_insensitive=True,
            owner_id=self.discord_settings.owner_id,
            help_command=EmbedHelpCommand(),
            *args,
            **kwargs,
        )

    async def retrieve_prefix(self, bot, message):
        if not message.guild or message.guild.id not in self.guild_prefixes:
            return self.config.default_prefix
        return self.guild_prefixes[message.guild.id]

    async def setup_hook(self) -> None:
        self.logger.info("Setting up RbbBot")
        await Tortoise.init(
            db_url=self.creds.db_url, modules={"models": ["rbb_bot.models"]}
        )
        ClientMixin.inject_client(self)

        for guild in await Guild.all():
            self.guild_prefixes[guild.id] = guild.prefix

        for cog in self.load_cogs:
            self.logger.debug(f"Loading {cog}")
            await self.load_extension(f"rbb_bot.cogs.{cog}")
        await self.load_extension("jishaku")
        self.logger.debug("Cogs loaded!")
        self.logging_task = asyncio.create_task(
            self.setup_logging(), name="discord-logging"
        )

    async def setup_logging(self):
        """Own channel setup and delivery as one task, including partial startup failure."""
        handler = None
        try:
            await self.wait_until_ready()
            handler = DiscordLogHandler(
                bot=self,
                logger_channel_id=self.discord_settings.logger_channel_id,
                my_id=self.discord_settings.owner_id,
                logger=self.logger,
            )
            handler.setLevel(logging.INFO)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            await handler.init()
            self.logger.addHandler(handler)
            self.logging_ready.set()
            await handler.run()
        except Exception:
            # Report through the local handler even if Discord logging failed.
            if handler is not None:
                self.logger.removeHandler(handler)
            self.logger.exception("Discord logging stopped")
        finally:
            if handler is not None:
                self.logger.removeHandler(handler)
                handler.close()
            # Scraping may proceed after a failed logging setup as well.
            self.logging_ready.set()

    async def on_connect(self):
        self.logger.info(f"Connected! Latency: {self.latency * 1000:.2f}ms")

    async def on_reconnect(self):
        self.logger.debug("Reconnected!")

    async def on_disconnect(self):
        self.logger.debug("Disconnected!")

    async def on_ready(self):
        await self.change_presence(
            activity=Activity(type=ActivityType.listening, name="Like a flower")
        )
        if self.user:
            self.logger.info(f"Logged in as {self.user} ({self.user.id})")
        else:
            self.logger.error("Logged in as None???")
        self.logger.info("RbbBot ready!")

    async def close(self):
        """Discord and the context manager may both request shutdown."""
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(
                self._close_resources(), name="bot-shutdown"
            )
        await asyncio.shield(self._shutdown_task)

    async def _close_resources(self):
        self.logger.info("Closing!")
        try:
            if self.logging_task is not None:
                self.logging_task.cancel()
                await asyncio.gather(self.logging_task, return_exceptions=True)
            # Bot.close unloads cogs before closing Discord's own HTTP client.
            await super().close()
        finally:
            ClientMixin.inject_client(None)
            await Tortoise.close_connections()
        # The launcher owns web_client and closes it after the bot context exits.

    async def process_commands(self, message: Message, /) -> None:
        if message.author.bot:
            return
        ctx = await self.get_context(message)
        await self.invoke(ctx)

    async def on_message(self, message: Message, /) -> None:
        await self.process_commands(message)

    async def get_confirmation(self, ctx, prompt, timeout=60):
        view = ConfirmView(ctx, timeout=timeout)
        view.message = await ctx.send(prompt, view=view)
        await view.wait()
        return view.confirmed

    async def send_error(
        self,
        ctx: Context | None = None,
        exc: Exception | None = None,
        stack_info=False,
        comment="",
    ):
        context = format_error_context(ctx) if ctx else ""
        msg = "\n".join(part for part in (comment, context) if part)
        self.logger.error(msg, exc_info=exc, stack_info=stack_info)
