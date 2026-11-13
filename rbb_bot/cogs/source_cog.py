from typing import Optional

from discord import RawReactionActionEvent
from discord.ext import commands
from discord.ext.commands import Cog, Context

from rbb_bot.application.sources.contracts import SourceRefused, SourceRequest
from rbb_bot.application.sources.lookup import CountSubmissions, FindSource
from rbb_bot.application.sources.moderate import ModerateSubmission
from rbb_bot.application.sources.submit import SubmitSource
from rbb_bot.infrastructure.sources.confirmation import (
    DiscordConfirmationPost,
    DiscordConfirmationPosts,
)
from rbb_bot.infrastructure.sources.emote_images import DiscordEmoteImages
from rbb_bot.infrastructure.sources.repository import TortoiseSourceRepository
from rbb_bot.settings.config import get_discord_settings
from rbb_bot.settings.const import BotEmojis
from rbb_bot.views.sources import (
    SubmissionsView,
    confirmation_prompt,
    refusal_reply,
    source_found,
)


class SourceCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.repository = TortoiseSourceRepository()

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

        lookup = await FindSource(self.repository).execute(emote_string)
        if lookup is None:
            return await ctx.send(f"Could not find any sources for {emote_string}")
        return await ctx.send(source_found(lookup))

    @source.command(
        name="add",
        brief="Add a source for an emote (Incorrect entries will be removed)",
    )
    @commands.guild_only()
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
        await self.submit(ctx, emote_string, source_url, event, source_date)

    @source.command(name="edit", brief="Edit source data for an emote")
    @commands.guild_only()
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
        await self.submit(ctx, emote_string, source_url, event, source_date, edit=True)

    async def submit(
        self,
        ctx: Context,
        emote_string: str,
        source_url: Optional[str],
        event: Optional[str],
        source_date: Optional[str],
        edit: bool = False,
    ):
        request = SourceRequest(
            emote=emote_string,
            source_url=source_url,
            event=event,
            source_date=source_date,
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            message_id=ctx.message.id,
            jump_url=ctx.message.jump_url,
            submitter_id=ctx.author.id,
            submitter_name=ctx.author.name,
        )
        submit = SubmitSource(
            self.repository,
            DiscordEmoteImages(self.bot.web_client),
            DiscordConfirmationPosts(
                self.bot, get_discord_settings().confirmation_channel_id
            ),
            self.bot.logger,
        )

        async def confirm(details):
            return await self.bot.get_confirmation(
                ctx, confirmation_prompt(details, edit)
            )

        try:
            submitted = await (submit.edit if edit else submit.add)(request, confirm)
        except SourceRefused as refusal:
            return await ctx.send(refusal_reply(refusal, ctx.prefix, source_date))
        if not submitted:
            return
        if edit:
            return await ctx.send("Source edited. Thank you! (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧")
        return await ctx.send("Source added. Thank you! (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧")

    @source.command(name="list", brief="List number of submissions by users")
    async def source_list(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()

        counts = await CountSubmissions(self.repository, self.current_name).execute()
        if not counts:
            return await ctx.send("No source submissions yet")
        view = SubmissionsView(ctx, list(counts), chunk_size=8)
        embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=embed, view=view)
        return view.message

    def current_name(self, user_id: int) -> str | None:
        user = self.bot.get_user(user_id)
        return user.name if user else None

    def moderation(self, payload: RawReactionActionEvent) -> ModerateSubmission:
        return ModerateSubmission(
            self.repository,
            DiscordConfirmationPost(self.bot, payload.channel_id, payload.message_id),
            self.bot.logger,
        )

    @staticmethod
    def from_owner_in_confirmation_channel(payload: RawReactionActionEvent) -> bool:
        settings = get_discord_settings()
        return (
            payload.channel_id == settings.confirmation_channel_id
            and payload.user_id == settings.owner_id
        )

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        if not self.from_owner_in_confirmation_channel(payload):
            return
        if payload.emoji.name == BotEmojis.CROSS:
            await self.moderation(payload).remove()
        elif payload.emoji.name == BotEmojis.HAMMER:
            moderation = self.moderation(payload)
            await moderation.blacklist_submitter()
            await moderation.remove()

    @Cog.listener()
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        if not self.from_owner_in_confirmation_channel(payload):
            return
        if payload.emoji.name == BotEmojis.HAMMER:
            await self.moderation(payload).lift_blacklist()


async def setup(bot):
    await bot.add_cog(SourceCog(bot))
