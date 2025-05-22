import asyncio
import logging

import discord
from discord.ext import commands
from utils.helpers import large_send


class DiscordLogHandler(logging.Handler):
    """Logging handler that sends logs to a Discord channel."""

    bot: commands.Bot
    log_ch: discord.TextChannel | None
    owner_ch: discord.DMChannel | None
    logger_channel_id: int
    logger: logging.Logger
    my_id: int
    message_queue: asyncio.Queue

    def __init__(
        self,
        bot: commands.Bot,
        logger_channel_id: int,
        my_id: int,
        logger: logging.Logger,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.log_ch = None
        self.owner_ch = None
        self.logger_channel_id = logger_channel_id
        self.my_id = my_id
        self.logger = logger
        self.message_queue = asyncio.Queue()

    async def start_logging(self):
        await self.init()
        await self.run()

    async def init(self):
        if not self.bot:
            return
        self.log_ch, self.owner_ch = await self.setup_logging_channels()
        if not self.log_ch and not self.owner_ch:
            return

    async def run(self):
        if not self.bot:
            return
        await self.bot.wait_until_ready()
        if not self.log_ch and not self.owner_ch:
            return

        while True:
            try:
                msg, level = await self.message_queue.get()
                msg = f"```\n{msg}\n```"
                if level == logging.ERROR or level == logging.CRITICAL:
                    if not self.owner_ch and self.log_ch:
                        await large_send(
                            self.log_ch, f"Could not get DM channel\n{msg}"
                        )
                    elif self.owner_ch:
                        await large_send(self.owner_ch, msg)

                elif self.log_ch:
                    await large_send(self.log_ch, msg)
                else:
                    print("Error in logger: No logging channel available")
                    print(msg)
            except Exception as e:
                print(f"Error in logger: {e}")
            await asyncio.sleep(1)

    def emit(self, record):
        if not self.bot:
            return
        msg = self.format(record)
        asyncio.create_task(self.message_queue.put((msg, record.levelno)))

    async def get_log_channel(
        self,
    ) -> discord.TextChannel | None:
        """Get a text channel by ID"""
        channel = self.bot.get_channel(self.logger_channel_id)
        if not channel:
            channel = await self.bot.fetch_channel(self.logger_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return None
        return channel

    async def get_dm_channel(
        self,
    ) -> discord.DMChannel | None:
        """Get a DM channel by user ID"""
        user = self.bot.get_user(self.my_id)
        if not user:
            try:
                user = await self.bot.fetch_user(self.my_id)
            except Exception as e:
                self.logger.error(f"Could not fetch user {self.my_id}: {e}")
                return None

        channel = user.dm_channel
        if not channel:
            return await user.create_dm()
        return channel

    async def setup_logging_channels(
        self,
    ) -> tuple[discord.TextChannel | None, discord.DMChannel | None]:
        """Set up logging channels"""
        log_ch = await self.get_log_channel()
        owner_ch = await self.get_dm_channel()
        if log_ch and owner_ch:
            self.logger.info(f"Logger channels set up: {log_ch.id}, {owner_ch.id}")
        elif log_ch:
            self.logger.info(f"Logger channel set up: {log_ch.id}")
        elif owner_ch:
            self.logger.info(f"Logger channel set up: {owner_ch.id}")
        else:
            print("Error setting up logger channels")
            return None, None
        return log_ch, owner_ch
