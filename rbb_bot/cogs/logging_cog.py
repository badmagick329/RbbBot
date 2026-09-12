from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context

from rbb_bot.application.guild_logging.configure import ConfigureLogging
from rbb_bot.infrastructure.guild_logging.repository import TortoiseLoggingRepository
from rbb_bot.views.guild_logging import logging_settings, member_event, message_event


class LoggingCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.configuration = ConfigureLogging(TortoiseLoggingRepository())

    @commands.hybrid_group(brief="Manage logging settings", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logging(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @logging.command(brief="Enable logging in a channel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def enable(self, ctx: Context, channel: discord.TextChannel):
        await ctx.defer()
        if channel.guild.id != ctx.guild.id:
            raise commands.BadArgument("The channel must belong to this server")
        await self.configuration.set_channel(ctx.guild.id, channel.id)
        await ctx.send(f"Logging enabled in {channel.mention}")

    @logging.command(brief="Disable logging")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def disable(self, ctx: Context):
        await ctx.defer()
        await self.configuration.set_channel(ctx.guild.id, None)
        await ctx.send("Logging disabled")

    @logging.command(name="setup", brief="Set which events are logged")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setup_(
        self,
        ctx: Context,
        member_join: Optional[bool] = None,
        member_leave: Optional[bool] = None,
        message_removed: Optional[bool] = None,
        message_edited: Optional[bool] = None,
    ):
        await ctx.defer()
        try:
            settings = await self.configuration.set_events(
                ctx.guild.id,
                member_join=member_join,
                member_leave=member_leave,
                message_removed=message_removed,
                message_edited=message_edited,
            )
        except ValueError as error:
            raise commands.BadArgument(str(error)) from error
        await ctx.send("Logging options updated", embed=logging_settings(settings))

    @logging.command(brief="Show logging settings")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def show(self, ctx: Context):
        await ctx.defer()
        await ctx.send(
            embed=logging_settings(await self.configuration.read(ctx.guild.id))
        )

    async def _send(self, guild_id, event, render):
        channel_id = await self.configuration.channel_for(guild_id, event)
        if channel_id is None:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(channel_id)
        payload = render()
        try:
            await channel.send(**payload)
        finally:
            if "file" in payload:
                payload["file"].close()

    @Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is not None and not message.author.bot:
            await self._send(
                message.guild.id, "message_removed", lambda: message_event(message)
            )

    @Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if (
            before.guild is not None
            and not before.author.bot
            and before.content != after.content
        ):
            await self._send(
                before.guild.id, "message_edited", lambda: message_event(before, after)
            )

    @Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self._send(
            member.guild.id, "member_join", lambda: member_event(member, True)
        )

    @Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self._send(
            member.guild.id, "member_leave", lambda: member_event(member, False)
        )


async def setup(bot):
    await bot.add_cog(LoggingCog(bot))
