import asyncio
import discord
from discord import TextChannel
from discord.ext import commands, tasks
from discord.ext.commands import Cog, Context

from rbb_bot.application.guild_lifecycle.cleanup import CleanupExpiredGuilds
from rbb_bot.application.guild_lifecycle.membership import (
    RecordGuildDeparture,
    RecordGuildRejoin,
)
from rbb_bot.application.guild_prefixes.contracts import PrefixRefused
from rbb_bot.application.guild_prefixes.prefixes import ManageGuildPrefix
from rbb_bot.infrastructure.guild_lifecycle.confirmation_posts import (
    GuildConfirmationPosts,
)
from rbb_bot.infrastructure.guild_lifecycle.guild_data import GuildDataService
from rbb_bot.infrastructure.guild_prefixes.repository import (
    TortoiseGuildPrefixRepository,
)
from rbb_bot.infrastructure.sources.confirmation import SourceConfirmationService
from rbb_bot.settings.const import DISCORD_MAX_MESSAGE
from rbb_bot.views.guild_prefixes import refusal_reply


class GuildCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        lifecycle = GuildDataService()
        self.prefixes = ManageGuildPrefix(
            TortoiseGuildPrefixRepository(), bot.guild_prefixes
        )
        self.record_departure = RecordGuildDeparture(lifecycle, bot.logger)
        self.record_rejoin = RecordGuildRejoin(lifecycle, bot.logger)
        self.cleanup = CleanupExpiredGuilds(
            lifecycle,
            GuildConfirmationPosts(SourceConfirmationService(bot)),
            bot.logger,
            self.guild_deleted,
        )

    def guild_deleted(self, guild_id: int):
        self.bot.guild_prefixes.pop(guild_id, None)
        # The tags cog may be unloaded; then there is no catalogue to refresh.
        if tag_catalog := getattr(self.bot, "tag_catalog", None):
            tag_catalog.invalidate(guild_id)

    async def cog_load(self):
        self.guild_cleanup_task.start()
        self.bot.logger.debug("GuildCog loaded!")

    async def cog_unload(self):
        task = self.guild_cleanup_task.get_task()
        self.guild_cleanup_task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        self.bot.logger.debug("GuildCog unloaded!")

    @tasks.loop(hours=24)
    async def guild_cleanup_task(self) -> None:
        try:
            await self.cleanup.execute()
        except Exception:
            self.bot.logger.exception("Guild cleanup task failed")

    @guild_cleanup_task.before_loop
    async def before_guild_cleanup_task(self) -> None:
        await self.bot.wait_until_ready()

    @commands.hybrid_command(brief="Show or set the prefix for this server")
    async def prefix(self, ctx: Context, new_prefix: str = None):
        """Show or set the prefix for this server."""
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if new_prefix is None:
            return await ctx.send(
                f"Current prefix: {await self.prefixes.read(ctx.guild.id)}"
            )
        try:
            await self.prefixes.set(ctx.guild.id, new_prefix)
        except PrefixRefused as refusal:
            return await ctx.send(refusal_reply(refusal, new_prefix))
        await ctx.send(f"Setting prefix to {new_prefix}")

    @commands.hybrid_command(brief="Tell me to send a message in a channel")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def say(self, ctx: Context, channel: TextChannel, *, message: str):
        """Send a message to a server channel on behalf of a moderator."""
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.send("I don't have permissions to send messages there")
        if len(message) > DISCORD_MAX_MESSAGE:
            return await ctx.send(
                f"Message must be less than {DISCORD_MAX_MESSAGE} characters"
            )
        await channel.send(message)
        await ctx.send("Message sent")

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await self.record_departure.execute(guild.id)

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.record_rejoin.execute(guild.id)


async def setup(bot):
    await bot.add_cog(GuildCog(bot))
