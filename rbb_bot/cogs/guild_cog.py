from typing import Optional

from discord import Member, TextChannel
from discord.ext import commands
from discord.ext.commands import Cog, Context
from models import Greeting, Guild
from settings.const import BOT_MAX_PREFIX, DISCORD_MAX_MESSAGE


class GuildCog(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.logger.debug("GuildCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("GuildCog unloaded!")

    @commands.hybrid_command(brief="Show or set the prefix for this server")
    async def prefix(self, ctx: Context, new_prefix: str = None):
        """
        Show or set the prefix for this server

        Parameter
        ---------
        new_prefix: str
            The prefix to set for this server
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if new_prefix is None:
            return await ctx.send(f"Current prefix: {guild.prefix}")
        elif len(new_prefix) > BOT_MAX_PREFIX:
            return await ctx.send(
                f"Prefix must be less than {BOT_MAX_PREFIX} characters"
            )
        if guild.prefix == new_prefix:
            return await ctx.send(f"Prefix is already set to {new_prefix}")

        guild.prefix = new_prefix
        await guild.save()
        self.bot.guild_prefixes[ctx.guild.id] = new_prefix
        await ctx.send(f"Setting prefix to {new_prefix}")

    @commands.hybrid_group(brief="Set a welcome message for new members")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def greet(self, ctx: Context):
        """
        Set a welcome message for new members
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @greet.command(brief="Enable welcome messages in the given channel")
    async def enable(self, ctx: Context, channel: TextChannel):
        """
        Enable welcome messages in the given channel

        Parameters
        ----------
        channel: TextChannel
            The channel to send welcome messages in (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if guild.greet_channel_id == channel.id:
            return await ctx.send(
                "Welcome messages are already enabled in this channel"
            )
        guild.greet_channel_id = channel.id
        await guild.save()
        await ctx.send(f"Set the welcome channel to {channel.mention}")

    @greet.command(brief="Disable welcome messages")
    async def disable(self, ctx: Context):
        """
        Disable welcome messages
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if guild.greet_channel_id is None:
            return await ctx.send("Welcome messages are already disabled")
        guild.greet_channel_id = None
        await guild.save()
        await ctx.send("Removed welcome channel")

    @greet.command(name="setup", brief="Setup the welcome message")
    async def setup_message(
        self,
        ctx: Context,
        title: Optional[str],
        message: Optional[str],
        show_member_count: Optional[bool] = True,
    ):
        """
        Setup the welcome message

        Parameters
        ----------
        title: str
            Title. Type {username} to mention username (Optional)
        message: str
            The message to send. Type {mention} to include mention (Optional)
        show_member_count: bool
            Whether to show the member count. (Default: True)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        greeting, _ = await Greeting.get_or_create(guild=guild)
        if title:
            if len(title) > Greeting.MAX_TITLE:
                return await ctx.send(
                    f"Title must be less than {Greeting.MAX_TITLE} characters"
                )
            greeting.title = title
        if message:
            if len(message) > Greeting.MAX_DESC:
                return await ctx.send(
                    f"Message must be less than {Greeting.MAX_DESC} characters"
                )
            greeting.description = message
        greeting.show_member_count = show_member_count
        await greeting.save()
        to_send = f"Message updated"
        if not guild.greet_channel_id:
            to_send = f"{to_send}. You can set the welcome channel with `{ctx.prefix}greet enable <channel>`"
        await ctx.send(to_send, embed=greeting.create_embed(ctx.author))

    @greet.command(brief="Preview current welcome message")
    async def preview(self, ctx: Context):
        """
        Preview current welcome message
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        greeting, _ = await Greeting.get_or_create(guild=guild)
        await ctx.send(embed=greeting.create_embed(ctx.author))

    @commands.hybrid_command(brief="Tell me to send a message in a channel")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def say(self, ctx: Context, channel: TextChannel, *, message: str):
        """
        Tell me to send a message in a channel

        Parameters
        ----------
        channel: TextChannel
            The channel to send the message in (Requires manage_messages)
        message: str
            The message to send (Required)
        """
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
    async def on_member_join(self, member: Member):
        guild = await Guild.get_or_none(id=member.guild.id)
        if not guild or not guild.greet_channel_id:
            return
        greeting = await Greeting.get_or_none(guild=guild)
        if not greeting:
            return
        channel = await guild.greet_channel()
        if not channel:
            return
        await channel.send(embed=greeting.create_embed(member))


async def setup(bot):
    await bot.add_cog(GuildCog(bot))
