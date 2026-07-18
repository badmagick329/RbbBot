import random
import re
from typing import Optional

import discord
from discord import Embed, Member, Message, Role, TextChannel
from discord.ext import commands, tasks
from discord.ext.commands import Cog, Context
from models import Greeting, Guild, JoinEvent
from services.auto_role_service import AutoRoleService
from settings.const import BOT_MAX_PREFIX, DISCORD_MAX_MESSAGE, BotEmojis
from utils.helpers import truncate
from utils.views import ListView

from rbb_bot.services.guild_data_service import GuildDataService
from rbb_bot.services.source_confirmation_service import SourceConfirmationService


class MessagesList(ListView):
    def create_embed(self, ids_and_responses: list[str]) -> Embed:
        header = ""
        if len(self.view_chunks) > 1:
            header += f"Page {self.current_page + 1} of {len(self.view_chunks)}\n"
        header += f"{len(self.list_items)} {'Messages' if len(self.list_items) > 1 else 'Message'} found"
        embed = Embed(title=header)

        for id_and_response in ids_and_responses:
            id, response = id_and_response
            embed.add_field(name=id, value=response, inline=False)
        return embed


class GuildCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.source_confirmation_service = SourceConfirmationService(bot)

    async def cog_load(self):
        self.guild_cleanup_task.start()
        self.bot.logger.debug("GuildCog loaded!")

    async def cog_unload(self):
        self.guild_cleanup_task.cancel()
        self.bot.logger.debug("GuildCog unloaded!")

    async def delete_source_confirmation_messages(
        self, guild_id: int, source_entries: list
    ) -> bool:
        """Delete source moderation posts before their database records are removed."""
        return await self.source_confirmation_service.delete_confirmation_messages(
            source_entries, scope="guild", scope_id=guild_id
        )

    async def cleanup_expired_guilds(self) -> None:
        candidates = await GuildDataService.expired_cleanup_candidates()
        deleted_guild_ids = []
        for guild in candidates:
            try:
                source_entries = await GuildDataService.source_entries_for_cleanup(
                    guild.id
                )
                if source_entries is None:
                    continue
                if not await self.delete_source_confirmation_messages(
                    guild.id, source_entries
                ):
                    continue
                if await GuildDataService.delete_guild_data(guild.id):
                    self.bot.guild_prefixes.pop(guild.id, None)
                    tag_service = getattr(self.bot, "tag_service", None)
                    if tag_service:
                        tag_service.remove_guild(guild.id)
                    deleted_guild_ids.append(guild.id)
                else:
                    self.bot.logger.warning(
                        "Guild cleanup skipped after source confirmation cleanup "
                        "guild_id=%s",
                        guild.id,
                    )
            except Exception:
                self.bot.logger.exception("Guild cleanup failed guild_id=%s", guild.id)

        if deleted_guild_ids:
            self.bot.logger.info(
                "Guild cleanup complete count=%s guild_ids=%s",
                len(deleted_guild_ids),
                ",".join(str(guild_id) for guild_id in deleted_guild_ids),
            )

    @tasks.loop(hours=24)
    async def guild_cleanup_task(self) -> None:
        try:
            await self.cleanup_expired_guilds()
        except Exception:
            self.bot.logger.exception("Guild cleanup task failed")

    @guild_cleanup_task.before_loop
    async def before_guild_cleanup_task(self) -> None:
        await self.bot.wait_until_ready()

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

    @commands.hybrid_group(brief="Set an embeded welcome message for new members")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def greet(self, ctx: Context):
        """
        Set an embeded welcome message for new members
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @greet.command(brief="Enable embeded welcome messages in the given channel")
    async def enable(self, ctx: Context, channel: TextChannel):
        """
        Enable embeded welcome messages in the given channel

        Parameters
        ----------
        channel: TextChannel
            The channel to send welcome messages in (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not ctx.guild:
            return await ctx.send("This command can only be used in a server.")

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if guild.greet_channel_id == channel.id:
            return await ctx.send(
                "Welcome messages are already enabled in this channel"
            )
        guild.greet_channel_id = channel.id  # type: ignore
        await guild.save()
        await ctx.send(f"Set the welcome channel to {channel.mention}")

    @greet.command(brief="Disable embeded welcome messages")
    async def disable(self, ctx: Context):
        """
        Disable embeded welcome messages
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not ctx.guild:
            return await ctx.send("This command can only be used in a server.")

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if guild.greet_channel_id is None:
            return await ctx.send("Welcome messages are already disabled")
        guild.greet_channel_id = None
        await guild.save()
        await ctx.send("Removed welcome channel")

    @greet.command(name="setup", brief="Setup embded welcome message")
    async def setup_message(
        self,
        ctx: Context,
        title: Optional[str],
        message: Optional[str],
        show_member_count: Optional[bool] = True,
    ):
        """
        Setup embeded welcome message

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

    @greet.command(brief="Preview current embeded welcome message")
    async def preview(self, ctx: Context):
        """
        Preview current embeded welcome message
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

    @commands.hybrid_group(brief="Setup welcome messages for new members")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def welcome(self, ctx: Context):
        """
        Setup welcome messages for new members
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @welcome.command(brief="Show or set channel for welcome messages", name="channel")
    @commands.guild_only()
    async def welcome_channel(self, ctx: Context, channel: Optional[TextChannel]):
        """
        Show or set channel for welcome messages

        Parameters
        ----------
        channel: TextChannel (Optional)
            The channel to send welcome messages in. Skip to show current channel
        """
        if ctx.guild is None:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        join_event, _ = await JoinEvent.get_or_create(guild=guild)
        if channel is None:
            if join_event.channel is None:
                return await ctx.send("No welcome channel set")
            return await ctx.send(
                f"Welcome messages will be sent in {join_event.channel.mention}"
            )
        if join_event.channel_id == channel.id:
            return await ctx.send(
                "Welcome messages are already enabled in this channel"
            )
        join_event.set_channel(channel)
        await join_event.save()
        perm_message = ""
        need_permission = (
            join_event.channel
            and not join_event.channel.permissions_for(ctx.guild.me).send_messages
        )
        if need_permission:
            perm_message = (
                f"\nI don't have permissions to send messages there right now"
            )
        await ctx.send(f"Set the welcome channel to {channel.mention}{perm_message}")

    @welcome.command(brief="Disable welcome messages in this channel", name="disable")
    @commands.guild_only()
    async def welcome_disable(self, ctx: Context):
        """
        Disable welcome messages in this channel
        """
        if ctx.guild is None:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        join_event, _ = await JoinEvent.get_or_create(guild=guild)
        if join_event.channel_id is None:
            return await ctx.send("Welcome messages are already disabled")
        join_event.set_channel(None)
        await join_event.save()
        await ctx.send("Disabled welcome messages")

    @welcome.command(brief="Add a welcome message for new members", name="message")
    @commands.guild_only()
    async def welcome_message(self, ctx: Context, message: str):
        """
        Add a welcome message for new members

        Parameters
        ----------
        message: str
            Add to the list of welcome messages. One of these will be randomly
            picked when someone joins
        """
        if ctx.guild is None:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        join_event, _ = await JoinEvent.get_or_create(guild=guild)
        if join_event.channel_id is None:
            return await ctx.send("No channel assigned for welcome messages.")
        if join_event.channel is None:
            join_event.set_channel(None)
            await join_event.save()
            return await ctx.send("Assigned channel no longer exists. Please reassign.")
        message = message.strip()
        if not message:
            return await ctx.send("Message cannot be empty")
        if len(message) > JoinEvent.MAX_MESSAGE:
            return await ctx.send(
                f"Message must be less than {JoinEvent.MAX_MESSAGE} characters"
            )
        _, added = await join_event.add_response(message)
        await join_event.save()
        if added:
            await ctx.send(f"Message added {BotEmojis.TICK}")
            need_permission = (
                join_event.channel
                and not join_event.channel.permissions_for(ctx.guild.me).send_messages
            )
            if need_permission:
                await ctx.send(
                    f"I don't have permissions to send messages in the assigned channel right now"
                )
        else:
            await ctx.send("Message already exists")

    @welcome.command(
        brief="Add all urls from a channel as welcome messages",
        name="add_urls",
    )
    @commands.guild_only()
    async def welcome_add_urls(
        self,
        ctx: Context,
        channel: TextChannel,
        include_attachments: Optional[bool] = True,
    ):
        """
        Add all urls from a channel as welcome messages

        Parameters
        ----------
        channel: TextChannel
            The channel to read urls from. Duplicates will be ignored
        include_attachments: bool (Optional)
            Whether to include attachments in the urls. Defaults to True
        """
        if ctx.guild is None:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        join_event, _ = await JoinEvent.get_or_create(guild=guild)
        if join_event.channel_id is None:
            return await ctx.send("No channel assigned for welcome messages.")
        if join_event.channel is None:
            join_event.set_channel(None)
            await join_event.save()
            return await ctx.send("Assigned channel no longer exists. Please reassign.")
        urls = await self.retrieve_urls(
            channel=channel, attachments=include_attachments
        )
        added_urls = 0
        saved_urls = 0
        for url in urls:
            _, added = await join_event.add_response(url)
            await join_event.save()
            if added:
                added_urls += 1
            else:
                saved_urls += 1
        message = ""
        if added_urls:
            message += f"{added_urls} messages added {BotEmojis.TICK}\n"
        if saved_urls:
            message += f"{saved_urls} messages were already saved"
        if not message:
            return await ctx.send(f"No urls found")
        await ctx.send(message)

    @welcome.command(
        brief="Read urls from channel and remove them from welcome messages",
        name="remove_urls",
    )
    @commands.guild_only()
    async def welcome_remove_urls(
        self,
        ctx: Context,
        channel: TextChannel,
        include_attachments: Optional[bool] = True,
    ):
        """
        Read urls from channel and remove them from welcome messages

        Parameters
        ----------
        channel: TextChannel
            The channel to read urls from
        include_attachments: bool (Optional)
            Whether to include attachments in the urls. Defaults to True
        """
        if ctx.guild is None:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        join_event, _ = await JoinEvent.get_or_create(guild=guild)
        if join_event.channel_id is None:
            return await ctx.send("No channel assigned for welcome messages.")
        if join_event.channel is None:
            join_event.set_channel(None)
            await join_event.save()
            return await ctx.send("Assigned channel no longer exists. Please reassign.")
        urls = await self.retrieve_urls(
            channel=channel, attachments=include_attachments
        )
        removed_urls = 0
        not_founds = 0
        for url in urls:
            removed = await join_event.remove_response(response_content=url)
            if removed:
                removed_urls += 1
            else:
                not_founds += 1

        message = ""
        if removed_urls:
            message += f"{removed_urls} messages removed {BotEmojis.TICK}\n"
        if not_founds:
            message += f"{not_founds} messages were not found"
        await ctx.send(message)

    @welcome.command(brief="Clear all welcome messages", name="clear")
    @commands.guild_only()
    async def welcome_clear(self, ctx: Context):
        """
        Clear all welcome messages
        """
        if ctx.guild is None:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        join_event, _ = await JoinEvent.get_or_create(guild=guild)
        await join_event.remove_responses()
        await join_event.save()
        await ctx.send("Cleared all welcome messages")

    @welcome.command(
        brief="Remove a welcome message by id or message (case sensitive)",
        name="remove",
    )
    @commands.guild_only()
    async def welcome_remove(
        self, ctx: Context, message_id: Optional[int], message_content: Optional[str]
    ):
        """
        Remove a welcome message by id or message (case sensitive)

        Parameters
        ----------
        message_id: int (Optional)
            The id of the message to remove
        message_content: str (Optional)
            The content of the message to remove
        """
        if not message_id and not message_content:
            return await ctx.send("You must provide either an id or message")
        if ctx.guild is None:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        join_event, _ = await JoinEvent.get_or_create(guild=guild)
        removed = await join_event.remove_response(message_id, message_content)
        if removed:
            await ctx.send(f"Message removed {BotEmojis.TICK}")
        else:
            await ctx.send(
                "Message not found. Use `welcome list` to see all messages and their ids"
            )

    @welcome.command(brief="List all welcome messages", name="list")
    @commands.guild_only()
    async def welcome_list(self, ctx: Context):
        """
        List all welcome messages
        """
        if ctx.guild is None:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        join_event, _ = await JoinEvent.get_or_create(guild=guild)
        if join_event.channel_id is None:
            await ctx.send("No channel assigned for welcome messages.")
        elif join_event.channel_id and join_event.channel is None:
            join_event.set_channel(None)
            await join_event.save()
            await ctx.send("Assigned channel no longer exists. Removing assignment.")
        messages = await join_event.responses()
        if not messages:
            # TODO:
            # Command example
            return await ctx.send("No welcome messages set")

        message_list = []
        for message in messages:
            message_list.append(
                (f"[{message.id}]", f"{truncate(message.content, 200)}")
            )

        # TODO:
        # Show assigned channel
        view = MessagesList(ctx, message_list)
        embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=embed, view=view)

    @welcome.command(
        brief="Preview sending a welcome message in this channel", name="preview"
    )
    @commands.guild_only()
    async def welcome_preview(self, ctx: Context):
        """
        Preview sending a welcome message in this channel
        """
        if ctx.guild is None:
            return
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not ctx.channel.permissions_for(ctx.guild.me).send_messages:
            return

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        join_event, _ = await JoinEvent.get_or_create(guild=guild)
        messages = await join_event.responses_as_str()
        if not messages:
            return await ctx.send("No welcome messages")
        await ctx.send(random.choice(messages))

    @commands.hybrid_group(
        brief="Manage auto roles for this server", invoke_without_command=True
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx: Context):
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @autorole.command(
        brief="Add a role that will be auto applied to new members", name="add"
    )
    async def add_role(self, ctx: Context, role: Role):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        result = await AutoRoleService.add_auto_role(ctx.guild.id, role.id)
        if result.is_err:
            self.bot.logger.error(f"Error adding auto role: {result.unwrap_err()}")
            return await ctx.send(
                f"Something went wrong while adding the role {role.mention}."
            )

        message = result.unwrap()
        if not ctx.guild.me.guild_permissions.manage_roles:
            message += "\nI will need the `Manage Roles` permission to apply roles to new members."
        await ctx.send(message)

    @autorole.command(
        brief="Apply auto roles to all members in the server", name="apply_all"
    )
    async def apply_all(self, ctx: Context, include_bots: bool = False):
        """
        Apply auto roles to all members in the server

        Parameters
        ----------
        include_bots: bool
            Whether to include bots in the auto role application. Defaults to False
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not ctx.guild:
            return await ctx.send("This command can only be used in a server.")

        if not ctx.guild.me.guild_permissions.manage_roles:
            return await ctx.send(
                "I need the `Manage Roles` permission to apply auto roles."
            )

        result = await AutoRoleService.apply_auto_roles(
            ctx.guild.id, ctx.guild.members, include_bots=include_bots
        )
        if result.is_err:
            self.bot.logger.error(f"Error applying auto roles: {result.unwrap_err()}")
            return await ctx.send("Something went wrong while applying auto roles.")

        await ctx.send(result.unwrap())

    @autorole.command(brief="Remove a role from the auto role list", name="remove")
    async def remove_role(self, ctx: Context, role: Role):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        result = await AutoRoleService.remove_auto_roles(ctx.guild.id, [role.id])
        if result.is_err:
            self.bot.logger.error(f"Error removing auto role: {result.unwrap_err()}")
            return await ctx.send(
                f"Something went wrong while removing the role {role.mention}."
            )

        message = result.unwrap()
        if not ctx.guild.me.guild_permissions.manage_roles:
            message += "\nI will need the `Manage Roles` permission to apply roles to new members."
        await ctx.send(message)

    @autorole.command(brief="List all auto roles", name="list")
    async def list_roles(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        result = await AutoRoleService.list_with_cleanup(ctx.guild.id)
        if result.is_err:
            self.bot.logger.error(f"Error retrieving auto roles: {result.unwrap_err()}")
            return await ctx.send("Something went wrong while retrieving auto roles.")

        existing_roles = result.unwrap()

        if not existing_roles:
            return await ctx.send("No auto roles set for this server.")

        embed = Embed(title="Auto Roles", description="List of auto roles")
        for role in existing_roles:
            embed.add_field(
                name=f"{role.name} `[{role.id}]`", value=f"{role.mention}", inline=False
            )

        await ctx.send(embed=embed)

    @autorole.command(brief="Remove all auto roles from list")
    async def remove_all(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        result = await AutoRoleService.remove_all_auto_roles(ctx.guild.id)
        if result.is_err:
            self.bot.logger.error(
                f"Error removing all auto roles: {result.unwrap_err()}"
            )
            return await ctx.send("Something went wrong while removing all auto roles.")

        await ctx.send(result.unwrap())

    # -----------------------
    # ----End of Commands----
    # -----------------------

    async def handle_greeting(self, guild: Guild, member: Member) -> Message | None:
        if not guild.greet_channel_id:
            return None
        greeting = await Greeting.get_or_none(guild=guild)
        if not greeting:
            return None
        channel = await guild.greet_channel()
        if not channel:
            return None
        return await channel.send(embed=greeting.create_embed(member))

    async def handle_join_event(self, guild: Guild) -> Message | None:
        join_event = await JoinEvent.get_or_none(guild=guild)
        if not join_event:
            return None
        channel = join_event.channel
        if not channel:
            return None
        messages = await join_event.responses_as_str()
        if not messages:
            return None
        return await channel.send(random.choice(messages))

    async def retrieve_urls(self, channel: TextChannel, attachments=True) -> list[str]:
        URL_REGEX = re.compile(r"https?://\S+\.\S+")
        urls = list()
        async for message in channel.history(limit=None):
            urls.extend(URL_REGEX.findall(message.content))
            if attachments and message.attachments:
                urls.extend(a.url for a in message.attachments)
        return urls

    async def handle_auto_role(self, member: Member) -> None:
        result = await AutoRoleService.list_with_cleanup(member.guild.id)
        if result.is_err:
            self.bot.logger.error(f"Error retrieving auto roles: {result.unwrap_err()}")
            return

        existing_roles = result.unwrap()
        if not existing_roles:
            return

        bot_member = member.guild.me
        if bot_member is None:
            self.bot.logger.error(
                f"Bot member unavailable for auto roles in guild {member.guild.id}"
            )
            return

        if not bot_member.guild_permissions.manage_roles:
            self.bot.logger.warning(
                f"Missing `Manage Roles` permission in {member.guild.name} for auto roles"
            )
            return

        await member.add_roles(*existing_roles)

    @Cog.listener()
    async def on_member_join(self, member: Member):
        guild = await Guild.get_or_none(id=member.guild.id)
        if not guild:
            return

        try:
            await self.handle_greeting(guild, member)
        except Exception:
            self.bot.logger.exception(
                "Member join greeting failed; continuing with remaining join actions "
                f"guild_id={member.guild.id} member_id={member.id}"
            )

        try:
            await self.handle_join_event(guild)
        except Exception:
            self.bot.logger.exception(
                "Member join event failed; continuing with remaining join actions "
                f"guild_id={member.guild.id} member_id={member.id}"
            )

        try:
            await self.handle_auto_role(member)
        except Exception:
            self.bot.logger.exception(
                "Member join autorole failed "
                f"guild_id={member.guild.id} member_id={member.id}"
            )

    @Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        try:
            if await GuildDataService.record_departure(guild.id):
                self.bot.logger.info("Guild marked departed guild_id=%s", guild.id)
        except Exception:
            self.bot.logger.exception(
                "Guild departure lifecycle handling failed guild_id=%s", guild.id
            )

    @Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        try:
            if await GuildDataService.record_rejoin(guild.id):
                self.bot.logger.info(
                    "Guild departure state cleared guild_id=%s", guild.id
                )
        except Exception:
            self.bot.logger.exception(
                "Guild rejoin lifecycle handling failed guild_id=%s", guild.id
            )


async def setup(bot):
    await bot.add_cog(GuildCog(bot))
