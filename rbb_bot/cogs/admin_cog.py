from typing import Literal, Optional

import discord
from discord.errors import Forbidden
from discord.ext import commands
from discord.ext.commands import Cog, Context, Greedy
from discord.ext.commands.errors import (
    BadArgument,
    BadLiteralArgument,
    ChannelNotFound,
    CommandInvokeError,
    CommandOnCooldown,
    ExpectedClosingQuoteError,
    MissingPermissions,
    MissingRequiredArgument,
    RoleNotFound,
)
from models import DiskCache

from rbb_bot.settings.const import BotEmojis
from rbb_bot.services.guild_data_service import GuildDataService
from rbb_bot.services.user_data_service import UserDataService
from rbb_bot.utils.error_logging import format_error_context


class AdminCog(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.logger.debug("AdminCog loaded!")

    async def cog_unload(self) -> None:
        self.bot.logger.debug("AdminCog unloaded!")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def ping(self, ctx):
        await ctx.send(f"🏓 {self.bot.latency * 1000:.2f}ms")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reload(self, ctx, ext: str):
        try:
            await self.bot.reload_extension(f"rbb_bot.cogs.{ext}")
            await ctx.message.add_reaction(BotEmojis.TICK)
        except commands.ExtensionNotLoaded:
            await self.bot.load_extension(f"rbb_bot.cogs.{ext}")
            await ctx.message.add_reaction(BotEmojis.TICK)
        except commands.ExtensionNotFound as e:
            await ctx.message.send(f"{BotEmojis.CROSS} {e}")
        except commands.ExtensionFailed as e:
            await ctx.send(f"{BotEmojis.CROSS} {e}")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def load(self, ctx, ext: str):
        try:
            await self.bot.load_extension(f"rbb_bot.cogs.{ext}")
            await ctx.message.add_reaction(BotEmojis.TICK)
        except (
            commands.ExtensionNotFound,
            commands.ExtensionFailed,
            commands.ExtensionAlreadyLoaded,
        ) as e:
            await ctx.send(f"{BotEmojis.CROSS} {e}")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def unload(self, ctx, ext: str):
        try:
            await self.bot.unload_extension(f"rbb_bot.cogs.{ext}")
            await ctx.message.add_reaction(BotEmojis.TICK)
        except (
            commands.ExtensionNotLoaded,
            commands.ExtensionNotFound,
            commands.ExtensionFailed,
        ) as e:
            await ctx.send(f"{BotEmojis.CROSS} {e}")

    @commands.command(brief="Sync hybrid commands")
    @commands.guild_only()
    @commands.is_owner()
    async def sync(
        self,
        ctx: Context,
        guilds: Greedy[discord.Object],
        spec: Optional[Literal["~", "*", "^"]] = None,
    ) -> None:
        """
        sync -> global sync
        sync ~ -> sync current guild
        sync * -> copies all global app commands to current guild and syncs
        sync ^ -> clears all commands from the current guild target and syncs (removes guild commands)
        sync id_1 id_2 -> syncs guilds with id 1 and 2
        """
        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                synced = []
            else:
                synced = await ctx.bot.tree.sync()

            await ctx.send(
                f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
            )
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1

        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")

    @commands.command(brief="Purge messages")
    @commands.guild_only()
    @commands.is_owner()
    async def clear(
        self, ctx, amount: int = 100, channel: Optional[discord.TextChannel] = None
    ):
        if channel is None:
            channel = ctx.channel
        if ctx.interaction:
            await ctx.interaction.response.defer()
        deleted = await channel.purge(limit=amount)
        return await ctx.send(f"Purged {len(deleted)} messages.", delete_after=5)

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reconcile_guilds(self, ctx: Context) -> None:
        """Mark legacy configured guilds no longer present in the ready guild cache."""
        try:
            guild_ids = await GuildDataService.reconcile_departed_guilds(
                [guild.id for guild in self.bot.guilds]
            )
        except Exception:
            self.bot.logger.exception("Legacy guild reconciliation failed")
            await ctx.send(f"{BotEmojis.CROSS} Guild reconciliation failed.")
            return

        self.bot.logger.info(
            "Legacy guild reconciliation complete count=%s guild_ids=%s",
            len(guild_ids),
            ",".join(str(guild_id) for guild_id in guild_ids),
        )
        await ctx.send(
            f"Marked {len(guild_ids)} legacy departed guild"
            f"{'s' if len(guild_ids) != 1 else ''}."
        )

    @commands.command(hidden=True)
    @commands.is_owner()
    async def privacy_status(self, ctx: Context, discord_user_id: int) -> None:
        """Report privacy-data counts without exposing user-provided content."""
        try:
            status = await UserDataService.status(discord_user_id)
        except Exception:
            self.bot.logger.exception(
                "Privacy status lookup failed discord_user_id=%s", discord_user_id
            )
            await ctx.send(f"{BotEmojis.CROSS} Privacy status lookup failed.")
            return

        await ctx.send(
            "Privacy status: "
            f"exists={status['exists']} reminders={status['reminder_count']} "
            f"source_entries={status['source_entry_count']} "
            f"tag_opt_out={status['tag_opt_out']} "
            f"has_blacklist={status['has_blacklist']}"
        )

    @commands.command(brief="Admin commands")
    @commands.is_owner()
    async def cmd(self, ctx, *, cmd_text: Optional[str] = ""):
        """
        Admin Commands

        clear cache
        update comebacks [optional list of urls separated by spaces]
        presence [activity] [status]
        """
        clean_text = cmd_text.strip().lower()
        if not clean_text:
            return await ctx.send_help(ctx.command)
        if clean_text == "clear cache":
            out = await DiskCache.all().delete()
            return await ctx.send(out)
        if clean_text.startswith("update comebacks"):
            urls = clean_text.split("update comebacks")[-1].strip()
            if not urls:
                urls = None

            kpop_cog = self.bot.get_cog("KpopCog")
            return await kpop_cog.update_comebacks(ctx, urls=urls)
        if clean_text.startswith("presence"):
            activity_options = {
                "playing": discord.ActivityType.playing,
                "streaming": discord.ActivityType.streaming,
                "listening": discord.ActivityType.listening,
                "watching": discord.ActivityType.watching,
                "competing": discord.ActivityType.competing,
            }
            args = clean_text.split(" ", 1)[-1].split(" ", 1)
            if len(args) == 1:
                return await ctx.send_help(ctx.command)
            activity, status = args
            if activity not in activity_options:
                return await ctx.send(
                    f"Activity options are: {', '.join(activity_options.keys())}"
                )
            await ctx.send(f"Changing presence to {activity} {status}")
            return await self.bot.change_presence(
                activity=discord.Activity(type=activity_options[activity], name=status)
            )

        return await ctx.send_help(ctx.command)

    @Cog.listener()
    async def on_command_error(self, ctx: Context, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, ExpectedClosingQuoteError):
            return await ctx.send(
                f"{BotEmojis.CROSS} One of the quotes around the arguments was missing."
            )
        if isinstance(error, CommandOnCooldown):
            return await ctx.send(
                f"{BotEmojis.IRENE_WARNING} You are on cooldown for {error.retry_after:.2f} seconds."
            )
        if isinstance(error, BadLiteralArgument):
            return await ctx.send(f"{BotEmojis.CROSS} Invalid Choice")

        errors = (
            RoleNotFound,
            ChannelNotFound,
            MissingPermissions,
            BadArgument,
            MissingRequiredArgument,
        )
        if isinstance(error, errors):
            return await ctx.send(f"{BotEmojis.CROSS} {error}")

        if isinstance(error, CommandInvokeError):
            if isinstance(error.original, Forbidden):
                await ctx.send(f"{BotEmojis.CROSS} {error.original}")

        self.bot.logger.error(format_error_context(ctx), exc_info=error)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
