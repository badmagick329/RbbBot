import asyncio
import logging
from pathlib import Path

import discord
from discord import Activity, ActivityType, Message
from discord.ext import commands
from discord.ext.commands import Context
from lib.discord_log_handler import DiscordLogHandler
from models import Guild
from tortoise import Tortoise
from utils.help_command import EmbedHelpCommand
from utils.views import ConfirmView

from rbb_bot.settings.config import Config, Creds
from rbb_bot.settings.ids import LOGGER_CHANNEL_ID, MY_ID
from rbb_bot.utils.mixins import ClientMixin


class RbbBot(commands.Bot):
    def __init__(
        self, config: Config, creds: Creds, logger, web_client, *args, **kwargs
    ):
        self.config = config
        self.creds = creds
        self.logger = logger
        self.web_client = web_client
        self.load_cogs = [
            c.stem
            for c in (Path(__file__).parent / "cogs").glob("*.py")
            if not c.stem.startswith("_")
        ]
        self.guild_prefixes = dict()
        self.logger_task = None
        self.bot_tasks = dict()
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
            owner_id=MY_ID,
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
        await Tortoise.init(db_url=self.creds.db_url, modules={"models": ["models"]})
        await Tortoise.generate_schemas(safe=True)
        ClientMixin.inject_client(self)

        for guild in await Guild.all():
            self.guild_prefixes[guild.id] = guild.prefix

        for cog in self.load_cogs:
            self.logger.debug(f"Loading {cog}")
            await self.load_extension(f"rbb_bot.cogs.{cog}")
        await self.load_extension("jishaku")
        self.logger.debug("Cogs loaded!")
        asyncio.create_task(self.setup_logging())

    async def setup_logging(self):
        await self.wait_until_ready()
        discord_log_handler = DiscordLogHandler(
            bot=self,
            logger_channel_id=LOGGER_CHANNEL_ID,
            my_id=MY_ID,
            logger=self.logger,
        )
        discord_log_handler.setLevel(logging.INFO)
        discord_log_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        self.logger.addHandler(discord_log_handler)
        self.logger_task = asyncio.create_task(discord_log_handler.start_logging())

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
        self.logger.info("Closing!")
        await self.web_client.close()
        await Tortoise.close_connections()
        await super().close()

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
        include_attachments=False,
        comment="",
    ):
        msg = comment
        if comment:
            msg += "\n"
        if ctx:
            if include_attachments and ctx.message.attachments:
                msg += "\n".join(a.url for a in ctx.message.attachments)
            if ctx.guild:
                msg += f"Guild: {ctx.guild.name} ({ctx.guild.id})\n"
            if ctx.command:
                msg += f"\n{ctx.command.qualified_name=}"
                params = list()
                args = ",".join([str(a) for a in ctx.args])
                if args:
                    params.append(f"args={args}")
                kwargs = ",".join(f"{k}:{v}." for k, v in ctx.kwargs.items())
                if kwargs:
                    params.append(f"kwargs={kwargs}")
                params = ", ".join(params)
                msg += f"\n{params}\n"
        self.logger.error(msg, exc_info=exc, stack_info=stack_info)
