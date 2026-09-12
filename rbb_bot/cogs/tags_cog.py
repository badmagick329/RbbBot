import random
from functools import wraps
from typing import Optional

from discord import Message, errors
from discord.ext import commands
from discord.ext.commands import Cog, Context

from rbb_bot.application.tags.contracts import TagSelector
from rbb_bot.application.tags.manage_tags import (
    AddTag,
    AddTagRequest,
    FindTag,
    ListTags,
    RenameTag,
    RenameTagRequest,
    RemoveTag,
    FindResponses,
    FindGfycatResponses,
    RemoveResponses,
)
from rbb_bot.application.tags.select_response import SelectTagResponse
from rbb_bot.domain.tags.rules import TagInputError, normalize_trigger
from rbb_bot.infrastructure.tags.catalog import CachedTagCatalog
from rbb_bot.infrastructure.tags.preferences import StoredTagPreferences
from rbb_bot.infrastructure.tags.repository import TortoiseTagRepository
from rbb_bot.settings.const import DISCORD_MAX_MESSAGE, BotEmojis
from rbb_bot.utils.helpers import truncate
from rbb_bot.views.tags import (
    TagsList,
    ResponsesList,
    tag_list_items,
    response_list_items,
)


def tag_input(callback):
    """Translate feature validation into the bot's existing command-error presentation."""

    @wraps(callback)
    async def invoke(*args, **kwargs):
        try:
            return await callback(*args, **kwargs)
        except TagInputError as error:
            raise commands.BadArgument(str(error)) from error

    return invoke


class TagsCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        repository = TortoiseTagRepository()
        self.catalog = CachedTagCatalog(repository)
        self.add_tag = AddTag(repository, self.catalog)
        self.find_tag = FindTag(repository)
        self.tags = ListTags(repository)
        self.rename_tag = RenameTag(repository, self.catalog)
        self.delete_tag = RemoveTag(repository, self.catalog)
        self.find_responses = FindResponses(repository)
        self.gfycat_responses = FindGfycatResponses(repository)
        self.delete_responses = RemoveResponses(repository, self.catalog)
        self.select_response = SelectTagResponse(
            self.catalog, repository, StoredTagPreferences(), random.choice
        )

    async def cog_load(self):
        await self.catalog.load()
        self.bot.tag_catalog = self.catalog
        self.bot.logger.debug("TagsCog loaded!")

    async def cog_unload(self):
        if getattr(self.bot, "tag_catalog", None) is self.catalog:
            del self.bot.tag_catalog
        self.bot.logger.debug("TagsCog unloaded!")

    @commands.hybrid_group(brief="Manage tags")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tag(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @tag.command(name="add", brief="Add a tag to this server")
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.guild_only()
    @tag_input
    async def add_(
        self, ctx: Context, trigger: str, response: str, inline: Optional[bool] = False
    ):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        result = await self.add_tag.execute(
            AddTagRequest(ctx.guild.id, trigger, response, inline)
        )
        if result.status == "duplicate":
            await ctx.send("This response already exists under this tag")
        else:
            await ctx.send(
                f"{BotEmojis.TICK} Tag `{result.tag.trigger}` {result.status}"
            )

    @tag.group(name="remove", brief="Remove a tag or response")
    async def remove_(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @remove_.command(name="tag", brief="Remove a tag by trigger or ID")
    @commands.guild_only()
    @tag_input
    async def remove_tag(
        self, ctx: Context, trigger: Optional[str] = None, tag_id: Optional[int] = None
    ):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        tag = await self.find_tag.execute(TagSelector(ctx.guild.id, tag_id, trigger))
        if tag is None:
            return await ctx.send("Tag not found")
        if not await self.bot.get_confirmation(
            ctx, f"Are you sure you want to delete the tag `{tag.trigger}`?"
        ):
            return
        removed = await self.delete_tag.execute(ctx.guild.id, tag.id)
        await ctx.send(
            f"{BotEmojis.TICK} Tag `{tag.trigger}` removed"
            if removed
            else "Tag no longer exists"
        )

    @remove_.command(name="response", brief="Remove a response by content or ID")
    @commands.guild_only()
    @tag_input
    async def remove_response(
        self,
        ctx: Context,
        response: Optional[str] = None,
        response_id: Optional[int] = None,
    ):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        responses = await self.find_responses.execute(
            ctx.guild.id, response_id, response
        )
        if not responses:
            return await ctx.send("This response does not exist")
        summary = truncate(responses[0].content, 300)
        if not await self.bot.get_confirmation(
            ctx, f"Are you sure you want to delete this response: {summary} ?"
        ):
            return
        deleted = await self.delete_responses.execute(
            ctx.guild.id, tuple(r.id for r in responses)
        )
        await ctx.send(
            f"{BotEmojis.TICK} Response `{summary}` removed"
            if deleted
            else "Response no longer exists"
        )

    @remove_.command(
        name="gfycat", brief="Remove responses using gfycat urls from this server"
    )
    @commands.guild_only()
    async def remove_gfycat(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        responses = await self.gfycat_responses.execute(ctx.guild.id)
        if not responses:
            return await ctx.send("No responses using gfycat urls found")
        prompt = "\n".join(
            [
                f"Confirm removal of {len(responses)} responses:",
                "```",
                *(r.content for r in responses),
            ]
        )
        prompt = truncate(prompt, DISCORD_MAX_MESSAGE - 4) + "\n```"
        if not await self.bot.get_confirmation(ctx, prompt):
            return
        deleted = await self.delete_responses.execute(
            ctx.guild.id, tuple(r.id for r in responses)
        )
        await ctx.send(f"{BotEmojis.TICK} {deleted} responses removed")

    @tag.command(name="list", brief="List all tags for this server")
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.guild_only()
    async def list_tags(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        tags = await self.tags.execute(ctx.guild.id)
        if not tags:
            return await ctx.send("No tags found")
        view = TagsList(ctx, tag_list_items(tags))
        view.message = await ctx.send(
            embed=view.create_embed(view.current_chunk), view=view
        )

    @tag.command(name="responses", brief="List responses for a tag by trigger or ID")
    @commands.guild_only()
    @commands.cooldown(2, 5, commands.BucketType.user)
    @tag_input
    async def list_responses(
        self, ctx: Context, trigger: Optional[str] = None, tag_id: Optional[int] = None
    ):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        tag = await self.find_tag.execute(TagSelector(ctx.guild.id, tag_id, trigger))
        if tag is None:
            return await ctx.send("Tag not found")
        if not tag.responses:
            return await ctx.send("No responses found for this tag")
        view = ResponsesList(ctx, response_list_items(tag.responses))
        view.message = await ctx.send(
            embed=view.create_embed(view.current_chunk), view=view
        )

    @tag.command(name="edit", brief="Edit a tag's trigger by ID or old trigger")
    @commands.guild_only()
    @tag_input
    async def edit_tag(
        self,
        ctx: Context,
        new_trigger: str,
        tag_id: Optional[int] = None,
        old_trigger: Optional[str] = None,
    ):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        new_trigger = normalize_trigger(new_trigger)
        tag = await self.find_tag.execute(
            TagSelector(ctx.guild.id, tag_id, old_trigger)
        )
        if tag is None:
            return await ctx.send("Tag not found")
        if not await self.bot.get_confirmation(
            ctx,
            f"Are you sure you want to edit the tag `{tag.trigger}` to `{new_trigger}`?",
        ):
            return
        result = await self.rename_tag.execute(
            RenameTagRequest(ctx.guild.id, tag.id, new_trigger)
        )
        await ctx.send(
            f"{BotEmojis.TICK} Tag `{result.trigger}` edited"
            if result
            else "Tag no longer exists"
        )

    @Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot or not message.guild:
            return
        # Check before requesting a context: it also reads message content.
        if not self.select_response.accepts_author(message.author.id):
            return
        ctx = await self.bot.get_context(message)
        if ctx.invoked_with:
            return
        try:
            response = await self.select_response.execute(
                message.guild.id, message.channel.id, message.author.id, message.content
            )
            if response is not None:
                await message.channel.send(response)
        except errors.Forbidden:
            pass
        except Exception as error:
            await self.bot.send_error(
                ctx, error, comment="Error sending tag response", stack_info=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(TagsCog(bot))
