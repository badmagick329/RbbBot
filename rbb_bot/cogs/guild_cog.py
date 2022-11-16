from typing import Optional

from discord import TextChannel, Member
from discord.ext import commands
from discord.ext.commands import Cog, Context
from models import Guild, Greeting
from settings.const import DISCORD_MAX_MESSAGE
from settings.ids import IRENE_CORD_ID, WHATEVER_ID, WHATEVER2_ID, TEST_CORD_ID
from pathlib import Path
import random
from datetime import datetime, timedelta


class GuildCog(Cog):
    # TODO Temp fix
    irenewaves_file = Path(__file__).parent.parent / "data" / "irenewaveids.txt"

    def __init__(self, bot):
        self.bot = bot
        self.irene_waves = list()
        gfycat_url_base = "https://gfycat.com/{gfy_name}"
        # Cooldown bucket to avoid greeting spam
        # List of tuples ("[member_id]_[guild_id]", datetime)
        self.cooldown_bucket = list()
        with open(self.irenewaves_file, "r") as f:
            for line in f.read().splitlines():
                self.irene_waves.append(gfycat_url_base.format(gfy_name=line.strip()))

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
        elif len(new_prefix) > Guild.MAX_PREFIX:
            return await ctx.send(
                f"Prefix must be less than {Guild.MAX_PREFIX} characters"
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

    def is_on_cooldown(self, id_key: str):
        self.cooldown_bucket = [entry for entry in self.cooldown_bucket if entry[1] > datetime.utcnow()]
        if id_key in [entry[0] for entry in self.cooldown_bucket]:
            return True

    @Cog.listener()
    async def on_member_join(self, member: Member):
        guild = await Guild.get_or_none(id=member.guild.id)
        if not guild or not guild.greet_channel_id:
            return
        # Fix for this being called multiple times on join for some guilds
        key = f"{member.guild.id}_{member.id}"
        if self.is_on_cooldown(key):
            return
        greeting = await Greeting.get_or_none(guild=guild)
        if not greeting:
            return
        channel = guild.greet_channel
        if not channel:
            return
        self.bot.logger.info(f"Sending welcome message to {member} in {channel} in {member.guild}")
        cooldown_dt = datetime.utcnow() + timedelta(minutes=1)
        self.cooldown_bucket.append((key, cooldown_dt))
        await channel.send(embed=greeting.create_embed(member))

        if guild.id in [IRENE_CORD_ID, WHATEVER_ID, WHATEVER2_ID, TEST_CORD_ID]:
            random_wave = random.choice(self.irene_waves)
            await channel.send(random_wave)


async def setup(bot):
    await bot.add_cog(GuildCog(bot))
