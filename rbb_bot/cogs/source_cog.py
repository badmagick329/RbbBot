import re
from datetime import date as Date
from datetime import datetime
from typing import Optional

from discord import Embed, RawReactionActionEvent
from discord.ext import commands
from discord.ext.commands import Cog, Context
from models import DiscordUser, SourceEntry

from rbb_bot.settings.const import BotEmojis
from rbb_bot.utils.helpers import emoji_regex
from rbb_bot.utils.views import ListView


class SubmissionsView(ListView):
    def create_embed(self, submissions: list[tuple[str, int]]) -> Embed:
        page_header = ""
        if len(self.view_chunks) > 1:
            page_header = f"\nPage {self.current_page + 1} of {len(self.view_chunks)}"
        header = f"Source Submissions by users{page_header}"

        embed = Embed(title=header)
        for user, count in submissions:
            embed.add_field(name=user, value=f"{count} submissions", inline=False)
        return embed


class SourceCog(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.logger.debug("SourceCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("SourceCog unloaded!")

    @commands.hybrid_group(
        brief="Look up the source for an emote", invoke_without_command=True
    )
    async def source(self, ctx: Context, *args, **kwargs):
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.find_source, *args, **kwargs)

    @source.command(name="find", brief="Look up the source for an emote")
    async def find_source(self, ctx: Context, emote_string: str = ""):
        """
        Look up the source for an emote

        Parameters
        ----------
        emote_string: str
            The emote to look up (Required)
        """
        if not emote_string:
            return await ctx.send_help(ctx.command)

        source_entries = (
            await SourceEntry.filter(emoji_string=emote_string)
            .order_by("conf_message_id")
            .prefetch_related("user")
        )
        if not source_entries:
            return await ctx.send(f"Could not find any sources for {emote_string}")
        source_url = None
        event = None
        source_date = None
        users = list()

        for source_entry in source_entries:
            if source_entry.source_url:
                source_url = source_entry.source_url
            if source_entry.event:
                event = source_entry.event
            if source_entry.source_date:
                source_date = source_entry.source_date
            if source_entry.user not in users:
                users.append(source_entry.user)

        message = ""
        if source_date:
            message = f"{source_date} "
        if event:
            message += f"{event}\n"
        if source_url:
            message += f"{source_url}\n"
        message += f"Submitted by {', '.join([user.cached_username for user in users])}"

        return await ctx.send(message)

    @source.command(
        name="add",
        brief="Add a source for an emote (Incorrect entries will be removed)",
    )
    async def add_source(
        self,
        ctx: Context,
        emote_string: str,
        source_url: str,
        event: Optional[str],
        source_date: Optional[str],
    ):
        """
        Add a source for an emote. (Incorrect entries will be removed)

        Parameters
        ----------
        emote_string: str
            The emote to add (Required)
        source_url: str
            The source URL (Required)
        event: Optional[str]
            The event of the source (Optional)
        source_date: Optional[str]
            The date of the source YYMMDD (Optional)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        await self.process_source_entry(
            ctx, emote_string, source_url, event, source_date
        )

    @source.command(name="edit", brief="Edit source data for an emote")
    async def source_edit(
        self,
        ctx: Context,
        emote_string: str,
        source_url: Optional[str],
        event: Optional[str],
        source_date: Optional[str],
    ):
        """
        Edit a source for an emote.

        Parameters
        ----------
        emote_string: str
            The emote to add (Required)
        source_url: str
            The source URL (Option)
        event: Optional[str]
            The event of the source (Optional)
        source_date: Optional[str]
            The date of the source YYMMDD (Optional)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        await self.process_source_entry(
            ctx, emote_string, source_url, event, source_date, edit_entry=True
        )

    async def process_source_entry(
        self,
        ctx: Context,
        emote_string: str,
        source_url: Optional[str],
        event: Optional[str],
        source_date: Optional[str],
        edit_entry: bool = False,
    ):
        # Check if user is blacklisted
        user, _ = await DiscordUser.get_or_create(
            id=ctx.author.id, defaults={"cached_username": ctx.author.name}
        )
        if not user.cached_username:
            user.cached_username = ctx.author.name
            await user.save()

        if user.blacklist and user.blacklist.get("source", None) == "blacklist":
            return await ctx.send("You are blacklisted from adding sources")

        # Initial validation
        if source_url:
            if len(source_url) > SourceEntry.MAX_CHAR_FIELD:
                return await ctx.send(
                    "Source URL is too long. Max "
                    f"{SourceEntry.MAX_CHAR_FIELD} characters"
                )
        if event:
            if len(event) > SourceEntry.MAX_CHAR_FIELD:
                return await ctx.send(
                    "Event is too long. Max " f"{SourceEntry.MAX_CHAR_FIELD} characters"
                )

        if not emoji_regex.search(emote_string):
            return await ctx.send(
                f"`{emote_string}` does not look like a valid emote string"
            )

        emoji_url = await self.fetch_emoji_url(emote_string)
        if not emoji_url:
            return await ctx.send(f"`{emote_string}` does not look like a valid emote")

        if edit_entry:
            if source_url:
                if not re.search(r"^https?://\S+\.\S+$", source_url):
                    return await ctx.send("Please provide a valid source URL")
        else:
            if not source_url:
                return await ctx.send("Please provide a source URL")
            if not re.search(r"^https?://\S+\.\S+$", source_url):
                return await ctx.send("Please provide a valid source URL")

        if source_date:
            validated_date = self.validate_source_date(source_date)
            if not validated_date:
                return await ctx.send(
                    (
                        f"`{source_date}` is not a valid date. Date format is YYMMDD. "
                        "Future dates are not permitted"
                    )
                )
            source_date = validated_date
        if event and event.strip():
            event = event.strip()

        if edit_entry:
            if not [a for a in [source_url, source_date, event] if a]:
                return await ctx.send(
                    "At least one of these is required: source_url, source_date, event"
                )

        # Get confirmation
        conf_prompt = ""
        if source_url:
            conf_prompt = f"Source: {source_url}\n"
        if source_date:
            conf_prompt += f"Date: {source_date}\n"
        if event:
            conf_prompt += f"Event: {event}\n"

        if edit_entry:
            conf_prompt += f"Edit these fields?"
        else:
            conf_prompt += f"Is this correct?"

        if not (await self.bot.get_confirmation(ctx, conf_prompt)):
            return

        # Create entry
        source_entry = SourceEntry(
            emoji_string=emote_string,
            emoji_url=emoji_url,
            source_url=source_url,
            source_date=source_date,
            event=event,
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            message_id=ctx.message.id,
            jump_url=ctx.message.jump_url,
            user=user,
        )

        await self.send_conf_message(source_entry)
        if edit_entry:
            return await ctx.send("Source edited. Thank you! (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧")
        else:
            return await ctx.send("Source added. Thank you! (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧")

    @source.command(name="list", brief="List number of submissions by users")
    async def source_list(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()

        source_entries = await SourceEntry.all().prefetch_related("user")
        discord_users = [entry.user for entry in source_entries]
        id_to_username = dict()
        for discord_user in discord_users:
            if discord_user.id in id_to_username:
                continue
            user = self.bot.get_user(discord_user.id)
            if user:
                id_to_username[discord_user.id] = user.name
            else:
                id_to_username[discord_user.id] = discord_user.cached_username

        username_count = dict()
        for discord_user in discord_users:
            username = id_to_username[discord_user.id]
            username_count.setdefault(username, 0)
            username_count[username] += 1

        username_count = sorted(
            username_count.items(), key=lambda x: x[1], reverse=True
        )
        view = SubmissionsView(ctx, username_count, chunk_size=8)
        embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=embed, view=view)
        return view.message

    async def send_conf_message(self, se: SourceEntry):
        """Sends a confirmation message for a source entry."""
        conf_msg_str = (
            f"Emote: `{se.emoji_string[0]} {se.emoji_string[1:]}`\n"
            f"Emoji url: {se.emoji_url}\n"
            f"Jump url: {se.jump_url}\n"
            f"Source link: {se.source_url}\n"
            f"Event: {se.event}\n"
            f"Date: {se.source_date}\n"
            f"User ID: {se.user.id}\n"
            f"Message ID: {se.message_id}\n"
            f"User name: {se.user.cached_username}\n"
        )
        conf_ch = self.bot.get_guild(se.conf_guild_id).get_channel(se.conf_channel_id)
        conf_msg = await conf_ch.send(conf_msg_str)
        await conf_msg.add_reaction(BotEmojis.CROSS)
        await conf_msg.add_reaction(BotEmojis.HAMMER)
        se.conf_message_id = conf_msg.id
        se.conf_jump_url = conf_msg.jump_url
        await se.save()

    def validate_source_date(self, date_str: str) -> Date | None:
        date = None
        try:
            date = datetime.strptime(date_str, "%y%m%d").date()
        except ValueError:
            pass
        if date and date > datetime.now().date():
            return None
        return date

    async def fetch_emoji_url(self, emoji_string) -> str | None:
        match = emoji_regex.search(emoji_string)
        if not match:
            return None
        emoji_id = match.group(3)
        image_format = "gif" if match.group(1) == "a" else "png"

        cdn_template = "https://cdn.discordapp.com/emojis/{emoji_id}.{image_format}"
        async with self.bot.web_client.get(
            cdn_template.format(emoji_id=emoji_id, image_format=image_format)
        ) as response:
            if response.status == 200:
                return cdn_template.format(emoji_id=emoji_id, image_format=image_format)

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        if payload.member.bot:
            return
        if payload.channel_id != SourceEntry.conf_channel_id:
            return
        if payload.emoji.name == BotEmojis.CROSS:
            await self.delete_via_reaction(payload)
        elif payload.emoji.name == BotEmojis.HAMMER:
            await self.ban_via_reaction(payload)
            await self.delete_via_reaction(payload)

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        if payload.channel_id != SourceEntry.conf_channel_id:
            return
        if payload.emoji.name == BotEmojis.HAMMER:
            await self.ban_via_reaction(payload, undo=True)

    async def ban_via_reaction(self, payload: RawReactionActionEvent, undo=False):
        message = await self.bot.get_channel(payload.channel_id).fetch_message(
            payload.message_id
        )
        user_id = self.get_from_lines(message.content.splitlines(), "user id")
        user = self.bot.get_user(int(user_id))
        if not user:
            return

        discord_user = await DiscordUser.get(id=user.id)

        if undo:
            if "source" in discord_user.blacklist:
                discord_user.blacklist.pop("source")
                await discord_user.save()
                self.bot.logger.info(
                    f"User no longer blacklisted from adding sources {user} ({user.id})"
                )

        else:
            if not discord_user.blacklist:
                discord_user.blacklist = dict()
            if discord_user.blacklist.get("source", None) == "blacklist":
                self.bot.logger.info("User already blacklisted from adding sources")
                return

            discord_user.blacklist["source"] = "blacklist"
            await discord_user.save()
            self.bot.logger.info(
                f"User blacklisted from adding sources {user} ({user.id})"
            )

    async def delete_via_reaction(self, payload: RawReactionActionEvent):
        message = await self.bot.get_channel(payload.channel_id).fetch_message(
            payload.message_id
        )
        original_message_id = self.get_from_lines(
            message.content.splitlines(), "message id"
        )
        source_entry = await SourceEntry.filter(message_id=int(original_message_id))
        if source_entry:
            await source_entry[0].delete()
        last_line = [line for line in message.content.splitlines()][-1]
        if last_line != "DELETED":
            await message.edit(content=f"{message.content}\n\nDELETED")

    def get_from_lines(self, lines: list[str], key: str) -> str | None:
        for line in lines:
            if line.lower().startswith(key):
                return line.split(":")[1].strip()
        return None


async def setup(bot):
    await bot.add_cog(SourceCog(bot))
