import asyncio
from datetime import timedelta
from typing import Optional

import discord
from discord import Emoji, TextChannel, Forbidden
from discord.ext import commands
from discord.ext.commands import Context, Cog
from discord.utils import sleep_until, utcnow
from models import Guild
from settings.const import DISCORD_MAX_MESSAGE
from utils.exceptions import NotOk, TimeoutError
from utils.helpers import emoji_regex
from utils.helpers import http_get


class EmojisCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        # Maps guild id to a datetime object of when updated emojis should be posted
        self.post_datetimes = dict()
        self.UPDATE_DELAY = 30

    async def cog_load(self):
        self.bot.bot_tasks.setdefault("post_datetimes", dict())
        self.post_datetimes = self.bot.bot_tasks["post_datetimes"]
        self.bot.logger.debug("EmojisCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("EmojisCog unloaded!")

    @staticmethod
    async def post_emojis(
        channel: TextChannel,
        guild: discord.Guild,
        emojis_message: str,
        delete_previous: bool,
        emojis_per_message: int = 15,
    ):
        """
        Post emojis to the channel
        """
        if delete_previous:
            await channel.purge(limit=None)
            async for message in channel.history(limit=100):
                await message.delete()

        emojis = guild.emojis
        static_emojis = list()
        animated_emojis = list()
        for e in emojis:
            if e.animated:
                animated_emojis.append(e)
            else:
                static_emojis.append(e)

        send_emojis = list()
        for to_send in [static_emojis, animated_emojis]:
            while to_send:
                send_emojis.append(str(to_send.pop(0)))
                if len(send_emojis) == emojis_per_message:
                    await channel.send("".join(send_emojis))
                    send_emojis = list()
            if send_emojis:
                await channel.send("".join(send_emojis))
                send_emojis = list()

        if emojis_message:
            await channel.send(emojis_message)

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
            image = await http_get(self.bot.web_client, url)
        except NotOk:
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
                await self.bot.send_error(ctx, e, "Error adding emote")
                return await ctx.send(f"Error adding emote: {e.text}")

        await ctx.send(f"Added emote {added_emoji}")

    @emote.command(brief="Remove one or more emotes from the server")
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

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if guild.emojis_channel_id == channel.id:
            self.bot.logger.debug(f"Channel already set to {channel}")
            return await ctx.send(
                "This channel is already assigned as the emotes channel"
            )
        guild.emojis_channel_id = channel.id
        guild.delete_emoji_messages = delete_previous
        await guild.save()
        await ctx.send(f"Assigned {guild.emojis_channel.mention} to post emotes in")

    @post.command(brief="Unassign the channel emotes are posted in")
    async def unassign(self, ctx: Context):
        """
        Unassign the channel emotes are posted in
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        guild.emojis_channel_id = None
        await guild.save()
        await ctx.send("Unassigned the channel emotes are posted in")

    @post.command(
        name="message",
        brief="Include a message after posting emotes. Set to clear to remove",
    )
    async def set_message(self, ctx: Context, *, message: Optional[str]):
        """
        Include a message after posting emotes. Set to clear to remove

        Parameters
        ----------
        message: str
            the message to include. set to clear to remove (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if message.strip().lower() == "clear":
            guild.emojis_channel_message = None
            await guild.save()
            await ctx.send(f"Cleared the message")
        else:
            if len(message) > DISCORD_MAX_MESSAGE:
                return await ctx.send(
                    f"Message is too long. Max length is {DISCORD_MAX_MESSAGE}"
                )
            guild.emojis_channel_message = message
            await guild.save()
            await ctx.send("Message set")

    @post.command(name="now", brief="Post emotes in the assigned channel now")
    @commands.cooldown(2, 10, commands.BucketType.guild)
    async def post_now(self, ctx: Context):
        """
        Post emotes in the assigned channel now
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if not guild.emojis_channel:
            return await ctx.send("No channel assigned to post emotes in")
        if not guild.emojis_channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.send(
                "I don't have manage messages permission in the emotes channel"
            )
        if not guild.emojis_channel.permissions_for(ctx.guild.me).read_message_history:
            return await ctx.send(
                "I don't have read message history permission in the emotes channel"
            )

        await ctx.send(f"Posting emotes in {guild.emojis_channel.mention}")
        try:
            await self.post_emojis(
                guild.emojis_channel,
                ctx.guild,
                guild.emojis_channel_message,
                guild.delete_emoji_messages,
            )
        except Forbidden as e:
            return await ctx.send(
                f"I do not have permission to post in the assigned channel"
            )
        except Exception as e:
            await self.bot.send_error(ctx, e, comment="Error posting emotes")

    async def post_updated_emojis(self, guild: Guild, discord_guild):
        if guild.id not in self.post_datetimes:
            await self.bot.send_error(
                comment=f"post_updated_emojis called for {discord_guild} "
                f"but no post_datetimes entry. {self.post_datetimes}"
            )
            return

        if self.post_datetimes[guild.id] <= utcnow():
            del self.post_datetimes[guild.id]
            await self.post_emojis(
                guild.emojis_channel,
                discord_guild,
                guild.emojis_channel_message,
                guild.delete_emoji_messages,
            )
        else:
            # await asyncio.sleep((self.post_datetimes[guild.id] - utcnow()).total_seconds())
            await sleep_until(self.post_datetimes[guild.id])
            await self.post_updated_emojis(guild, discord_guild)

    @Cog.listener()
    async def on_guild_emojis_update(
        self, guild: Guild, before: list[Emoji], after: list[Emoji]
    ):
        guild_settings = await Guild.get_or_none(id=guild.id)
        if guild_settings is None or guild_settings.emojis_channel is None:
            return

        if self.post_datetimes.get(guild.id) is None:
            self.bot.logger.debug(
                f"Emojis updated in guild {guild}. Scheduling post in {self.UPDATE_DELAY} seconds"
            )
            self.post_datetimes[guild.id] = utcnow() + timedelta(
                seconds=self.UPDATE_DELAY
            )
            asyncio.create_task(self.post_updated_emojis(guild_settings, guild))
        else:
            self.post_datetimes[guild.id] = utcnow() + timedelta(
                seconds=self.UPDATE_DELAY
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(EmojisCog(bot))
