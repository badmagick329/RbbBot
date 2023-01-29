import random
import re
from typing import Optional

from discord import Embed, Message
from discord.ext import commands
from discord.ext.commands import Cog, Context
from models import Guild, Response, Tag
from tortoise.functions import Count
from tortoise.transactions import atomic
from utils.helpers import truncate
from utils.views import ListView

from rbb_bot.settings.const import DISCORD_MAX_MESSAGE, BotEmojis
from rbb_bot.utils.decorators import log_command


class TagsList(ListView):
    def create_embed(self, tags_and_responses: list[str]) -> Embed:
        header = (
            f"{len(self.list_items)} {'Tags' if len(self.list_items) > 1 else 'Tag'}"
        )
        embed = Embed(
            title=f"Page {self.current_page + 1} of {len(self.view_chunks)}\n{header}"
        )

        for tnr in tags_and_responses:
            tag, response = tnr
            embed.add_field(name=tag, value=response, inline=False)

        return embed


class ResponsesList(ListView):
    def create_embed(self, ids_and_responses: list[str]) -> Embed:
        header = f"{len(self.list_items)} {'Responses' if len(self.list_items) > 1 else 'Response'} found"
        embed = Embed(
            title=f"Page {self.current_page + 1} of {len(self.view_chunks)}\n{header}"
        )

        for id_and_response in ids_and_responses:
            id, response = id_and_response
            embed.add_field(name=id, value=response, inline=False)
        return embed


class TagsCog(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.logger.debug("TagsCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("TagsCog unloaded!")

    @commands.hybrid_group(brief="Manage tags")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tag(self, ctx: Context):
        """
        Add, remove or edit tags for this server
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @tag.command(name="add", brief="Add a tag to this server")
    @commands.cooldown(2, 5, commands.BucketType.user)
    @log_command(command_name="tag add")
    async def add_(
        self, ctx: Context, trigger: str, response: str, inline: Optional[bool] = False
    ):
        """
        Add a tag to this server

        Parameters
        ----------
        trigger: str
            The text that triggers this response (Required)
        response: str
            The response that gets sent (Required)
        inline: str
            When False the trigger has to match the message exactly (Optional)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if len(trigger) > Tag.MAX_TRIGGER:
            return await ctx.send(
                f"{BotEmojis.CROSS} The trigger is too long. Max {Tag.MAX_TRIGGER} characters"
            )
        if len(response) > DISCORD_MAX_MESSAGE:
            return await ctx.send(
                f"{BotEmojis.CROSS} The response is too long. "
                f"Max {DISCORD_MAX_MESSAGE} characters"
            )

        trigger = trigger.lower().strip()
        response_content = response.strip()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)

        @atomic()
        async def add_tag(guild, trigger, response_content, inline) -> Optional[Tag]:
            saved_tag = await Tag.filter(guild=guild, trigger=trigger).first()
            created = False
            if not saved_tag:
                created = True
                saved_tag = await Tag.create(
                    guild=guild, trigger=trigger, inline=inline
                )

            response = await saved_tag.responses.filter(
                guild=guild, content=response_content
            ).first()
            if not response:
                response = await Response.create(guild=guild, content=response_content)
                await saved_tag.responses.add(response)
                await saved_tag.save()
                return saved_tag, created
            return None

        result = await add_tag(guild, trigger, response_content, inline)
        if result:
            tag, created = result
            to_send = f"{BotEmojis.TICK} Tag `{tag.trigger}` {'created' if created else 'updated'}"
            if ctx.interaction:
                await ctx.interaction.response.send_message(to_send)
            else:
                await ctx.send(to_send)
        else:
            await ctx.send(f"This response already exists under this tag")

    @tag.group(name="remove", brief="Remove a tag or response")
    async def remove_(self, ctx: Context):
        """
        Remove a tag or response
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @remove_.command(
        name="tag",
        brief="Remove a tag from this server. Either trigger or tag_id is required",
    )
    @log_command(command_name="tag remove tag")
    async def remove_tag(
        self, ctx: Context, trigger: Optional[str], tag_id: Optional[int]
    ):
        """
        Remove a tag from this server. Either trigger or tag_id is required

        Parameters
        ----------
        trigger: str
            The text that triggers this response (Optional)
        tag_id: int
            The id of the tag to remove (Optional)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not trigger and not tag_id:
            if ctx.interaction:
                return await ctx.interaction.response.send_message(
                    "Either trigger or tag_id is required", ephemeral=True
                )
            else:
                return await ctx.send_help(ctx.command)

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        tag = await Tag.by_id_or_trigger(guild, tag_id, trigger)
        if not tag:
            return await ctx.send(f"Tag not found")

        @atomic()
        async def remove(tag):
            r_ids = await tag.responses.all().values_list("id", flat=True)
            await Response.filter(id__in=r_ids).delete()
            await tag.delete()

        prompt = f"Are you sure you want to delete the tag `{trigger}`?"
        if not (await self.bot.get_confirmation(ctx, prompt)):
            return

        await remove(tag)
        await ctx.send(f"{BotEmojis.TICK} Tag `{trigger}` removed")

    @remove_.command(
        name="response",
        brief="Remove a response from this server. Either response or response_id is required",
    )
    @log_command(command_name="tag remove response")
    async def remove_response(
        self, ctx: Context, response: Optional[str], response_id: Optional[int]
    ):
        """
        Remove a response from this server. Either response or response_id is required

        Parameters
        ----------
        response: str
            The response that gets sent (Optional)
        response_id: int
            The id of the response (Optional)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not response and not response_id:
            if ctx.interaction:
                return await ctx.interaction.response.send_message(
                    "Either response or response_id is required", ephemeral=True
                )
            else:
                return await ctx.send_help(ctx.command)

        response_content = response
        guild, _ = await Guild.get_or_create(id=ctx.guild.id)

        responses = await Response.by_id_or_content(
            guild, response_id, response_content
        )
        if not responses:
            return await ctx.send(f"This response does not exist")

        @atomic()
        async def remove(responses):
            deleted_responses = await Response.filter(
                id__in=[r.id for r in responses]
            ).delete()
            if deleted_responses:
                remove_tags = (
                    await Tag.filter(guild=guild)
                    .annotate(response_count=Count("responses"))
                    .filter(response_count=0)
                    .all()
                )
                await Tag.filter(id__in=[t.id for t in remove_tags]).delete()

        response_truncated = truncate(response_content, 300)
        prompt = (
            f"Are you sure you want to delete this response: {response_truncated} ?"
        )
        if not (await self.bot.get_confirmation(ctx, prompt)):
            return
        await remove(responses)
        await ctx.send(f"{BotEmojis.TICK} Response`{response_truncated}` removed")

    @tag.command(name="list", brief="List all tags for this server")
    @commands.cooldown(2, 5, commands.BucketType.user)
    @log_command(command_name="tag list")
    async def list_tags(self, ctx: Context):
        """
        List all tags for this server
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        tags = await Tag.filter(guild=guild).prefetch_related("responses").all()
        if not tags:
            return await ctx.send(f"No tags found")

        tags_and_responses = []
        for tag in tags:
            response_str = truncate(tag.responses[0].content, 160)
            if len(tag.responses) > 1:
                response_str += f" and {len(tag.responses) - 1} more"

            tags_and_responses.append(
                (f"[{tag.id}] {tag.trigger}\nUsed {tag.use_count} times", response_str)
            )

        view = TagsList(ctx, tags_and_responses)
        embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=embed, view=view)

    @tag.command(
        name="responses",
        brief="List all responses for this tag. Either trigger or tag_id is required",
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    @log_command(command_name="tag responses")
    async def list_responses(
        self, ctx: Context, trigger: Optional[str], tag_id: Optional[int]
    ):
        """
        List all responses for this tag. Either trigger or tag_id is required

        Parameters
        ----------
        trigger: str
            The text that triggers this response (Optional)
        tag_id: int
            The id of the tag (Optional)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not trigger and not tag_id:
            if ctx.interaction:
                return await ctx.interaction.response.send_message(
                    "Either trigger or tag_id is required", ephemeral=True
                )
            else:
                return await ctx.send_help(ctx.command)
        guild, _ = await Guild.get_or_create(id=ctx.guild.id)

        tag = await Tag.by_id_or_trigger(guild, tag_id, trigger)
        if not tag:
            return await ctx.send(f"Tag not found")

        responses = await tag.responses.all()
        if not responses:
            await tag.delete()
            await self.bot.send_error(
                ctx=ctx, message=f"No responses found for tag `{trigger}`"
            )
            return await ctx.send(
                f"No responses found for this tag. Tag has been deleted"
            )

        response_list = []
        for response in responses:
            response_list.append(
                (f"[{response.id}]", f"{truncate(response.content, 160)}")
            )

        view = ResponsesList(ctx, response_list)
        embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=embed, view=view)

    @tag.command(
        name="edit",
        brief="Edit a tag's trigger. Either tag_id or old_trigger is required",
    )
    @log_command(command_name="tag edit")
    async def edit_tag(
        self,
        ctx: Context,
        new_trigger: str,
        tag_id: Optional[int],
        old_trigger: Optional[str],
    ):
        """
        Edit a tag's trigger. Either tag_id or old_trigger is required

        Parameters
        ----------
        new_trigger: str
            The new trigger of the tag (Required)
        tag_id: int
            The id of the tag (Optional)
        old_trigger: str
            The old trigger of the tag (Optional)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        new_trigger = new_trigger.lower().strip()
        if not tag_id and not old_trigger:
            if ctx.interaction:
                return await ctx.interaction.response.send_message(
                    "Either tag_id or old_trigger is required", ephemeral=True
                )
            else:
                return await ctx.send_help(ctx.command)

        if len(new_trigger) > Tag.MAX_TRIGGER:
            return await ctx.send(
                f"Trigger can't be longer than {Tag.MAX_TRIGGER} characters"
            )

        if tag := await Tag.get_or_none(trigger=new_trigger):
            return await ctx.send(f"Tag with trigger `{new_trigger}` already exists")

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        tag = await Tag.by_id_or_trigger(guild, tag_id, old_trigger)
        if not tag:
            return await ctx.send(f"Tag not found")

        prompt = (
            f"Are you sure you want to edit the tag `{tag.trigger}` to `{new_trigger}`?"
        )
        if not (await self.bot.get_confirmation(ctx, prompt)):
            return
        tag.trigger = new_trigger
        await tag.save()
        await ctx.send(f"{BotEmojis.TICK} Tag `{tag.trigger}` edited")

    @staticmethod
    def get_triggered_tag(tags: list[Tag], message: str) -> Tag | None:
        """
        Get the tag that was triggered by the message

        Parameters
        ----------
        tags: list[Tag]
            The tags to check
        message: str
            The message to check

        Returns
        -------
        Tag | None
            The tag that was triggered or None if no tag was triggered
        """
        tags = [t for t in tags if t.trigger in message]

        for tag in [t for t in tags if not t.inline]:
            if tag.trigger == message:
                return tag

        for tag in [t for t in tags if t.inline]:
            if re.search("".join(["\\b", tag.trigger, "\\b"]), message):
                return tag
        return None

    @Cog.listener()
    async def on_message(self, message: Message):
        if message.author.bot or not message.guild:
            return
        ctx = await self.bot.get_context(message)
        if ctx.invoked_with:
            return

        ci_content = message.content.lower().strip()
        channel = message.channel

        guild, _ = await Guild.get_or_create(id=message.guild.id)
        if guild.emojis_channel and message.channel == guild.emojis_channel:
            return
        tags = await Tag.filter(guild=guild).prefetch_related("responses")
        if not tags:
            return

        tag = self.get_triggered_tag(tags, ci_content)
        if tag:
            try:
                responses = await tag.responses.all()
                if not responses:
                    await tag.delete()
                    await self.bot.send_error(
                        ctx=ctx, message=f"No responses found for tag `{tag.trigger}`"
                    )
                    return
                response = random.choice(responses)
                tag.use_count += 1
                await tag.save()
                await channel.send(response.content)
            except Exception as e:
                await self.bot.send_error(
                    ctx, e, comment="Error sending tag response", stack_info=e
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(TagsCog(bot))
