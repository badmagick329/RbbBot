import discord
from discord import TextChannel
from discord.ext import commands, tasks
from discord.ext.commands import Cog, Context

from rbb_bot.models import Guild
from rbb_bot.services.guild_data_service import GuildDataService
from rbb_bot.services.source_confirmation_service import SourceConfirmationService
from rbb_bot.settings.const import BOT_MAX_PREFIX, DISCORD_MAX_MESSAGE


class GuildCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.source_confirmation_service = SourceConfirmationService(bot)

    async def cog_load(self):
        self.guild_cleanup_task.start()
        self.bot.logger.debug("GuildCog loaded!")

    async def cog_unload(self):
        self.guild_cleanup_task.cancel()
        self.bot.logger.debug("GuildCog unloaded!")

    async def delete_source_confirmation_messages(
        self, guild_id: int, source_entries: list
    ) -> bool:
        """Delete source moderation posts before their database records are removed."""
        return await self.source_confirmation_service.delete_confirmation_messages(
            source_entries, scope="guild", scope_id=guild_id
        )

    async def cleanup_expired_guilds(self) -> None:
        candidates = await GuildDataService.expired_cleanup_candidates()
        deleted_guild_ids = []
        for guild in candidates:
            try:
                source_entries = await GuildDataService.source_entries_for_cleanup(
                    guild.id
                )
                if source_entries is None:
                    continue
                if not await self.delete_source_confirmation_messages(
                    guild.id, source_entries
                ):
                    continue
                if await GuildDataService.delete_guild_data(guild.id):
                    self.bot.guild_prefixes.pop(guild.id, None)
                    tag_service = getattr(self.bot, "tag_service", None)
                    if tag_service:
                        tag_service.remove_guild(guild.id)
                    deleted_guild_ids.append(guild.id)
                else:
                    self.bot.logger.warning(
                        "Guild cleanup skipped after source confirmation cleanup "
                        "guild_id=%s",
                        guild.id,
                    )
            except Exception:
                self.bot.logger.exception("Guild cleanup failed guild_id=%s", guild.id)

        if deleted_guild_ids:
            self.bot.logger.info(
                "Guild cleanup complete count=%s guild_ids=%s",
                len(deleted_guild_ids),
                ",".join(str(guild_id) for guild_id in deleted_guild_ids),
            )

    @tasks.loop(hours=24)
    async def guild_cleanup_task(self) -> None:
        try:
            await self.cleanup_expired_guilds()
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

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if new_prefix is None:
            return await ctx.send(f"Current prefix: {guild.prefix}")
        if len(new_prefix) > BOT_MAX_PREFIX:
            return await ctx.send(
                f"Prefix must be less than {BOT_MAX_PREFIX} characters"
            )
        if guild.prefix == new_prefix:
            return await ctx.send(f"Prefix is already set to {new_prefix}")

        guild.prefix = new_prefix
        await guild.save()
        self.bot.guild_prefixes[ctx.guild.id] = new_prefix
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
        try:
            if await GuildDataService.record_departure(guild.id):
                self.bot.logger.info("Guild marked departed guild_id=%s", guild.id)
        except Exception:
            self.bot.logger.exception(
                "Guild departure lifecycle handling failed guild_id=%s", guild.id
            )

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        try:
            if await GuildDataService.record_rejoin(guild.id):
                self.bot.logger.info(
                    "Guild departure state cleared guild_id=%s", guild.id
                )
        except Exception:
            self.bot.logger.exception(
                "Guild rejoin lifecycle handling failed guild_id=%s", guild.id
            )


async def setup(bot):
    await bot.add_cog(GuildCog(bot))
