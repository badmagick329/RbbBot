import io
from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context
from services.guild_logging_service import GuildLoggingService
from settings.const import MAX_EMBED_FIELD_VALUE

from rbb_bot.core.formatted_timestamps import MemberTimestamps, MessageTimestamps


class LoggingCog(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.logger.debug("LoadingCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("LoadingCog unloaded!")

    @commands.hybrid_group(brief="Manage logging settings", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def logging(self, ctx: Context):
        """
        Manage logging settings for the server.
        """
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @logging.command(brief="Enable logging for a channel")
    async def enable(self, ctx: Context, channel: discord.TextChannel):
        """
        Enable logging for a specific channel

        Parameters
        ----------
        channel: discord.TextChannel
            The channel to enable logging for
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        result = await GuildLoggingService.enable(ctx.guild, channel)
        if result.is_ok:
            await ctx.send(result.unwrap())
        else:
            self.bot.logger.error(f"Error enabling logging: {result.unwrap_err()}")
            await ctx.send("An unexpected error occurred. Please try again later.")

    @logging.command(brief="Disable logging")
    async def disable(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        result = await GuildLoggingService.disable(ctx.guild)
        if result.is_ok:
            await ctx.send(result.unwrap())
        else:
            self.bot.logger.error(f"Error disabling logging: {result.unwrap_err()}")
            await ctx.send("An unexpected error occurred. Please try again later.")

    @logging.command(name="setup", brief="Setup logging for the server.")
    async def setup_(
        self,
        ctx: Context,
        member_join: Optional[bool],
        member_leave: Optional[bool],
        message_removed: Optional[bool],
        message_edited: Optional[bool],
    ):
        """
        Setup logging for the server.

        Atleast one of the parameters must be provided to enable logging:

        member_join, member_leave, message_removed, message_edited


        Examples:

        {prefix}logging setup off on on off

        {prefix}logging setup f f t


        Parameters
        ----------
        member_join: Optional[bool]
            Enable logging for member joins (Optional)
        member_leave: Optional[bool]
            Enable logging for member leaves (Optional)
        message_removed: Optional[bool]
            Enable logging for message removals (Optional)
        message_edited: Optional[bool]
            Enable logging for message edits (Optional)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        result = await GuildLoggingService.setup(
            guild=ctx.guild,
            member_join=member_join,
            member_leave=member_leave,
            message_removed=message_removed,
            message_edited=message_edited,
        )
        if result.is_ok:
            await ctx.send(result.unwrap())
        else:
            self.bot.logger.error(f"Error setting up logging: {result.unwrap_err()}")
            await ctx.send("An unexpected error occurred. Please try again later.")

    @logging.command(brief="Show logging config for the server.")
    async def show(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        result = await GuildLoggingService.show(ctx.guild)
        if result.is_ok:
            config = result.unwrap()
            if config is None:
                await ctx.send("Logging is not configured for this server.")
            else:
                embed = discord.Embed(
                    title="Logging Configuration", color=discord.Color.blue()
                )
                embed.add_field(name="Log Channel", value=config.channel or "None")
                embed.add_field(
                    name="Member Join", value=str(config.member_join), inline=False
                )
                embed.add_field(
                    name="Member Leave", value=str(config.member_leave), inline=False
                )
                embed.add_field(
                    name="Message Removed",
                    value=str(config.message_removed),
                    inline=False,
                )
                embed.add_field(
                    name="Message Edited",
                    value=str(config.message_edited),
                    inline=False,
                )
                await ctx.send(embed=embed)
        else:
            self.bot.logger.error(
                f"Error showing logging config: {result.unwrap_err()}"
            )
            await ctx.send("An unexpected error occurred. Please try again later.")

    @Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        ctx: Context = await self.bot.get_context(message)
        if ctx.invoked_with:
            return

        message_timestamps = MessageTimestamps(message)

        logging_channel_result = await GuildLoggingService.logging_channel_for(
            message.guild, "message_removed"
        )
        if logging_channel_result.is_err:
            self.bot.logger.error(
                f"Error retrieving logging channel: {logging_channel_result.unwrap_err()}"
            )
            return

        logging_channel = logging_channel_result.unwrap()
        if not logging_channel:
            return

        author = message.author
        channel = message.channel
        embed = discord.Embed(
            title="Message Deleted",
            color=discord.Color.red(),
        )
        embed.set_author(
            name=f"{author.name}({author.id})",
            icon_url=author.display_avatar.url,
        )
        embed.add_field(name="Channel", value=channel.mention, inline=True)  # type: ignore
        embed.add_field(name="Message ID", value=f"`{message.id}`", inline=True)
        embed.add_field(
            name="Created at",
            value=f"{message_timestamps.created}",
            inline=False,
        )

        if len(message.content) < MAX_EMBED_FIELD_VALUE:
            embed.add_field(
                name="Content", value=message.content or "No content", inline=False
            )
            await logging_channel.send(embed=embed)
        else:
            embed.add_field(
                name="Content",
                value=f"Message was too long ({len(message.content)} chars), attached as a file.",
                inline=False,
            )
            buffer = io.StringIO(message.content)
            file = discord.File(fp=buffer, filename=f"deleted-message_{message.id}.txt")  # type: ignore
            await logging_channel.send(embed=embed, file=file)

    @Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return

        logging_channel_result = await GuildLoggingService.logging_channel_for(
            before.guild, "message_edited"
        )
        if logging_channel_result.is_err:
            self.bot.logger.error(
                f"Error retrieving logging channel: {logging_channel_result.unwrap_err()}"
            )
            return

        logging_channel = logging_channel_result.unwrap()
        if not logging_channel:
            return

        message_timestamps = MessageTimestamps(after)

        embed = discord.Embed(
            title="Message Edited",
            color=discord.Color.orange(),
        )
        embed.set_author(
            name=f"{before.author.name}({before.author.id})",
            icon_url=before.author.display_avatar.url,
        )
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)  # type:ignore
        embed.add_field(name="Message ID", value=f"`{before.id}`", inline=True)
        embed.add_field(
            name="Created at",
            value=f"{message_timestamps.created}",
            inline=False,
        )

        if before.content == after.content:
            return

        if (
            len(before.content) < MAX_EMBED_FIELD_VALUE
            and len(after.content) < MAX_EMBED_FIELD_VALUE
        ):
            embed.add_field(
                name="Before", value=before.content or "No content", inline=False
            )
            embed.add_field(
                name="After", value=after.content or "No content", inline=False
            )
            await logging_channel.send(embed=embed)
        elif len(before.content) < MAX_EMBED_FIELD_VALUE:
            embed.add_field(
                name="Before",
                value=before.content or "No content",
                inline=False,
            )
            embed.add_field(
                name="After",
                value=f"Message was too long ({len(after.content)} chars), attached as a file.",
                inline=False,
            )
            buffer = io.StringIO(after.content)
            file = discord.File(
                fp=buffer,  # type: ignore
                filename=f"edited-message-after_{after.id}.txt",
            )
            await logging_channel.send(embed=embed, file=file)
        elif len(after.content) < MAX_EMBED_FIELD_VALUE:
            embed.add_field(
                name="Before",
                value=f"Message was too long ({len(before.content)} chars), attached as a file.",
                inline=False,
            )
            embed.add_field(
                name="After", value=after.content or "No content", inline=False
            )
            buffer = io.StringIO(before.content)
            file = discord.File(
                fp=buffer,  # type: ignore
                filename=f"edited-message-before_{before.id}.txt",
            )
            await logging_channel.send(embed=embed, file=file)
        else:
            embed.add_field(
                name="Messages",
                value=f"Both messages were too long ({len(before.content)} and {len(after.content)} chars), attached as files.",
                inline=False,
            )

            buffer = io.StringIO(
                f"Before:\n{before.content}\n\nAfter:\n{after.content}"
            )
            file = discord.File(fp=buffer, filename=f"edited-message_{before.id}.txt")  # type: ignore
            await logging_channel.send(embed=embed, file=file)

    @Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.guild:
            return

        logging_channel_result = await GuildLoggingService.logging_channel_for(
            member.guild, "member_join"
        )
        if logging_channel_result.is_err:
            self.bot.logger.error(
                f"Error retrieving logging channel: {logging_channel_result.unwrap_err()}"
            )
            return

        logging_channel = logging_channel_result.unwrap()
        if not logging_channel:
            return

        formatted_timestamps = MemberTimestamps(member)

        embed = discord.Embed(
            title="Member Joined",
            color=discord.Color.green(),
        )
        embed.set_author(
            name=f"{member.name}({member.id})",
            icon_url=member.display_avatar.url,
        )
        embed.add_field(
            name="Account Created",
            value=f"{formatted_timestamps.account_created} ~ {formatted_timestamps.account_created_relative}",
        )
        await logging_channel.send(embed=embed)

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member.guild:
            return

        logging_channel_result = await GuildLoggingService.logging_channel_for(
            member.guild, "member_leave"
        )
        if logging_channel_result.is_err:
            self.bot.logger.error(
                f"Error retrieving logging channel: {logging_channel_result.unwrap_err()}"
            )
            return

        logging_channel = logging_channel_result.unwrap()
        formatted_timestamps = MemberTimestamps(member)

        if not logging_channel:
            return

        embed = discord.Embed(
            title="Member Left",
            color=discord.Color.red(),
        )
        embed.set_author(
            name=f"{member.name}({member.id})",
            icon_url=member.display_avatar.url,
        )
        embed.add_field(
            name="Account Created",
            value=f"{formatted_timestamps.account_created} ~ {formatted_timestamps.account_created_relative}",
        )
        if member.joined_at:
            embed.add_field(
                name="Joined At",
                value=f"{formatted_timestamps.joined_at} ~ {formatted_timestamps.joined_at_relative}",
            )
        else:
            embed.add_field(
                name="Joined At",
                value="Unknown",
            )

        await logging_channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(LoggingCog(bot))
