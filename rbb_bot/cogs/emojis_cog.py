import asyncio
from datetime import timedelta
from typing import Optional

import discord
from discord import Emoji, TextChannel
from discord.ext import commands
from discord.ext.commands import Cog, Context
from discord.utils import sleep_until, utcnow

from rbb_bot.application.emotes.configure import ConfigureEmoteChannel
from rbb_bot.application.emotes.contracts import (
    EmoteChannelRefused,
    EmoteChannelUnavailable,
)
from rbb_bot.application.emotes.post_emotes import PostEmotesNow, RepostEmotes
from rbb_bot.infrastructure.emotes.discord_poster import DiscordEmotePoster
from rbb_bot.infrastructure.emotes.repository import TortoiseEmoteChannelRepository
from rbb_bot.infrastructure.http.public_download import UnsafeDownload
from rbb_bot.utils.exceptions import NotOk, TimeoutError
from rbb_bot.utils.helpers import emoji_regex, http_get
from rbb_bot.views.emotes import refusal_reply


class EmojisCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.repository = TortoiseEmoteChannelRepository()
        self.configure = ConfigureEmoteChannel(self.repository, self.channel_changed)
        # Maps guild id to a datetime object of when updated emojis should be posted
        self.post_datetimes = dict()
        self.post_tasks = set()
        self.UPDATE_DELAY = 30

    def channel_changed(self, guild_id: int):
        # The tags cog may be unloaded; then there is no catalogue to refresh.
        if tag_catalog := getattr(self.bot, "tag_catalog", None):
            tag_catalog.invalidate(guild_id)

    async def cog_load(self):
        self.bot.logger.debug("EmojisCog loaded!")

    async def cog_unload(self):
        tasks = tuple(self.post_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.post_datetimes.clear()
        self.bot.logger.debug("EmojisCog unloaded!")

    @commands.hybrid_group(brief="Add, remove or rename emotes in the server")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def emote(self, ctx: Context):
        """
        Add, remove or rename emotes in the server
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @emote.command(brief="Add an emote to the server")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def add(self, ctx: Context, name: str, url: Optional[str] = None):
        """
        Add an emote to the server

        Parameters
        ----------
        name: str
            The name of the emote, without ":" (Required)
        url: Optional[str]
            Url of the image/gif to add as an emote. Attachment used if no url (max 256kb)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        # Get the image url
        if url is None:
            if ctx.message.attachments:
                url = ctx.message.attachments[0].url
            else:
                await ctx.send_help(ctx.command)
                return await ctx.send("No url or attachment provided.")

        # Download image
        try:
            image = await http_get(url)
        except (NotOk, UnsafeDownload):
            return await ctx.send("Error fetching image")
        except TimeoutError:
            return await ctx.send("Timed out fetching image")

        # Try to add the emoji
        try:
            added_emoji = await ctx.guild.create_custom_emoji(name=name, image=image)

        except ValueError as e:
            return await ctx.send(f"Error adding emote: {e}")
        except discord.HTTPException as e:
            if "Missing Permissions" in e.text:
                return await ctx.send("I don't have permission to add emotes")
            elif "In name:" in e.text:
                return await ctx.send("There was a problem with the given name")
            elif "In image:" in e.text:
                return await ctx.send("The image was too large")
            else:
                await self.bot.send_error(ctx, e, comment="Error adding emote")
                return await ctx.send(f"Error adding emote: {e.text}")

        await ctx.send(f"Added emote {added_emoji}")

    @emote.command(brief="Remove one or more emotes from the server")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def remove(self, ctx: Context, *, emotes: str):
        """
        Remove one or more emotes from the server

        Parameters
        ----------
        emotes: str
            The emotes to remove (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        names_and_emojis = [
            (r[1], discord.utils.get(ctx.guild.emojis, id=int(r[2])))
            for r in emoji_regex.findall(emotes)
        ]
        if not names_and_emojis:
            return await ctx.send("No emotes found in message")

        # Remove the emojis
        final_message = list()
        for name, emoji in names_and_emojis:
            if emoji not in ctx.guild.emojis:
                final_message.append(f"Emote {name} not found")
                continue
            try:
                await ctx.guild.delete_emoji(emoji)
                final_message.append(f"Deleted emote {name} ({emoji.url})")
            except discord.Forbidden:
                final_message.append("I don't have permission to remove emotes")
                break
            except discord.HTTPException as e:
                final_message.append(f"Error removing emote: {e.text}")

        if final_message:
            await ctx.send("\n".join(final_message))

    @emote.command(brief="Rename an emote")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def rename(self, ctx: Context, new_name: str, emote: Emoji):
        """
        Rename an emote

        Parameters
        ----------
        new_name: str
            The new name for the emote (Required)
        emote: Emoji
            The emote to rename (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if emote not in ctx.guild.emojis:
            return await ctx.send("This emote is not from this server")

        try:
            new_emote = await emote.edit(name=new_name)
        except discord.HTTPException:
            return await ctx.send(
                "Could not change name. Make sure the new name is valid"
            )

        await ctx.send(f"Changed name of emote {new_emote} to {new_name}")

    @emote.command(brief="List available number of slots for emotes")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def slots(self, ctx: Context):
        """
        List available number of slots for emotes
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        animated_emotes = [e for e in ctx.guild.emojis if e.animated]
        static_emotes = [e for e in ctx.guild.emojis if not e.animated]
        await ctx.send(
            f"Static emote slots used: {len(static_emotes)}/{ctx.guild.emoji_limit}\n"
            f"Animated emote slots used: {len(animated_emotes)}/{ctx.guild.emoji_limit}"
        )

    @emote.group(brief="Manage posting emotes in a channel")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def post(self, ctx: Context):
        """
        Manage posting emotes in a channel
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @post.command(
        brief="Assign a channel to post emotes in. "
        "I need manage messages and read message history permission"
    )
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def assign(
        self, ctx: Context, channel: TextChannel, delete_previous: bool = True
    ):
        """
        Assign a channel to post emotes in. I need manage messages and read message history permission

        Parameters
        ----------
        channel: TextChannel
            the channel to post emotes in (Required)
        delete_previous: bool
            delete previous messages in the channel? (Default: True)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        try:
            await self.configure.assign(ctx.guild.id, channel.id, delete_previous)
        except EmoteChannelRefused as refusal:
            return await ctx.send(refusal_reply(refusal))
        await ctx.send(f"Assigned {channel.mention} to post emotes in")

    @post.command(brief="Unassign the channel emotes are posted in")
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def unassign(self, ctx: Context):
        """
        Unassign the channel emotes are posted in
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        await self.configure.unassign(ctx.guild.id)
        await ctx.send("Unassigned the channel emotes are posted in")

    @post.command(
        name="message",
        brief="Include a message after posting emotes. Set to clear to remove",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def set_message(self, ctx: Context, *, message: str):
        """
        Include a message after posting emotes. Set to clear to remove

        Parameters
        ----------
        message: str
            the message to include. set to clear to remove (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if message.strip().lower() == "clear":
            await self.configure.clear_message(ctx.guild.id)
            return await ctx.send("Cleared the message")
        try:
            await self.configure.set_message(ctx.guild.id, message)
        except EmoteChannelRefused as refusal:
            return await ctx.send(refusal_reply(refusal))
        await ctx.send("Message set")

    @post.command(name="now", brief="Post emotes in the assigned channel now")
    @commands.cooldown(2, 10, commands.BucketType.guild)
    @commands.guild_only()
    @commands.has_permissions(manage_emojis=True)
    async def post_now(self, ctx: Context):
        """
        Post emotes in the assigned channel now
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        announced = False

        async def announce(channel_id):
            nonlocal announced
            await ctx.send(f"Posting emotes in <#{channel_id}>")
            announced = True

        post = PostEmotesNow(self.repository, DiscordEmotePoster(self.bot, ctx.guild))
        try:
            await post.execute(ctx.guild.id, announce)
        except EmoteChannelRefused as refusal:
            return await ctx.send(refusal_reply(refusal))
        except EmoteChannelUnavailable as error:
            if not error.deleted:
                return await ctx.send(
                    "I do not have permission to post in the assigned channel"
                )
            await self.bot.send_error(ctx, error, comment="Error posting emotes")
        except Exception as error:
            # Failures before the announcement (reading settings, resolving the
            # channel) go to the global command error handler; once posting has
            # started, the requester already has a reply and the owner gets the error.
            if not announced:
                raise
            await self.bot.send_error(ctx, error, comment="Error posting emotes")

    async def post_updated_emojis(self, discord_guild: discord.Guild):
        guild_id = discord_guild.id
        while guild_id in self.post_datetimes:
            deadline = self.post_datetimes[guild_id]
            if deadline > utcnow():
                await sleep_until(deadline)
                continue
            del self.post_datetimes[guild_id]
            await RepostEmotes(
                self.repository,
                DiscordEmotePoster(self.bot, discord_guild),
                self.bot.guild_notices,
                self.bot.logger,
            ).execute(guild_id)
            return

    def post_finished(self, task):
        self.post_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            self.bot.logger.error("Emoji update failed", exc_info=task.exception())

    @Cog.listener()
    async def on_guild_emojis_update(
        self, guild: discord.Guild, before: list[Emoji], after: list[Emoji]
    ):
        if (await self.configure.read(guild.id)).channel_id is None:
            return

        if self.post_datetimes.get(guild.id) is None:
            self.bot.logger.debug(
                f"Emojis updated in guild {guild}. Scheduling post in {self.UPDATE_DELAY} seconds"
            )
            self.post_datetimes[guild.id] = utcnow() + timedelta(
                seconds=self.UPDATE_DELAY
            )
            task = asyncio.create_task(self.post_updated_emojis(guild))
            self.post_tasks.add(task)
            task.add_done_callback(self.post_finished)
        else:
            self.post_datetimes[guild.id] = utcnow() + timedelta(
                seconds=self.UPDATE_DELAY
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(EmojisCog(bot))
