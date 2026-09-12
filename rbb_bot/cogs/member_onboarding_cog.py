import random
from functools import wraps
from typing import Optional

from discord import HTTPException, Member, Role, TextChannel
from discord.ext import commands
from discord.ext.commands import Cog, Context

from rbb_bot.application.member_onboarding import HandleMemberJoin
from rbb_bot.application.member_onboarding.configure_greeting import (
    ConfigureGreeting,
    UpdateGreeting,
)
from rbb_bot.application.member_onboarding.welcome_messages import (
    ConfigureWelcomeMessages,
    ImportWelcomeUrls,
)
from rbb_bot.application.member_onboarding.auto_roles import (
    ConfigureAutoRoles,
    ApplyAutoRoles,
)
from rbb_bot.application.member_onboarding.join_actions import ConfiguredJoinActions
from rbb_bot.domain.member_onboarding.configuration import (
    DEFAULT_GREETING,
    OnboardingInputError,
)
from rbb_bot.infrastructure.member_onboarding.repository import (
    TortoiseOnboardingRepository,
)
from rbb_bot.infrastructure.member_onboarding.discord_actions import (
    DiscordOnboarding,
    DiscordWelcomeUrls,
    member_info,
)
from rbb_bot.views.member_onboarding import (
    create_greeting_embed,
    MessagesList,
    role_embed,
    assignment_summary,
)


def configuration_command(permission):
    """Apply authorization to every hybrid subcommand and translate feature input errors."""

    def decorate(callback):
        @wraps(callback)
        async def invoke(self, ctx, *args, **kwargs):
            if ctx.interaction:
                await ctx.interaction.response.defer()
            try:
                return await callback(self, ctx, *args, **kwargs)
            except OnboardingInputError as error:
                raise commands.BadArgument(str(error)) from error

        return commands.guild_only()(
            commands.has_permissions(**{permission: True})(invoke)
        )

    return decorate


class MemberOnboardingCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.repository = TortoiseOnboardingRepository()
        discord = self.discord = DiscordOnboarding(bot)
        self.greetings = ConfigureGreeting(self.repository, discord)
        self.messages = ConfigureWelcomeMessages(self.repository, discord)
        self.import_urls = ImportWelcomeUrls(self.messages, DiscordWelcomeUrls(bot))
        self.roles = ConfigureAutoRoles(self.repository, discord)
        self.assign_roles = ApplyAutoRoles(self.roles, discord)

    @commands.hybrid_group(brief="Configure embedded greetings")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greet(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @greet.command(brief="Enable embedded greetings in a channel")
    @configuration_command("manage_guild")
    async def enable(self, ctx: Context, channel: TextChannel):
        await self.greetings.set_channel(ctx.guild.id, channel.id)
        await ctx.send(f"Set the welcome channel to {channel.mention}")

    @greet.command(brief="Disable embedded greetings")
    @configuration_command("manage_guild")
    async def disable(self, ctx: Context):
        await self.greetings.set_channel(ctx.guild.id, None)
        await ctx.send("Removed welcome channel")

    @greet.command(name="setup", brief="Set the embedded greeting template")
    @configuration_command("manage_guild")
    async def setup_message(
        self,
        ctx: Context,
        title: Optional[str] = None,
        message: Optional[str] = None,
        show_member_count: bool = True,
    ):
        """Use {username} in the title and {mention} in the message."""
        settings = await self.greetings.execute(
            UpdateGreeting(ctx.guild.id, title, message, show_member_count)
        )
        text = "Message updated"
        if settings.channel_id is None:
            text += f". Set the channel with `{ctx.prefix}greet enable <channel>`"
        await ctx.send(text, embed=create_greeting_embed(settings.template, ctx.author))

    @greet.command(brief="Preview the current embedded greeting")
    @configuration_command("manage_guild")
    async def preview(self, ctx: Context):
        settings = await self.greetings.read(ctx.guild.id)
        await ctx.send(
            embed=create_greeting_embed(
                settings.template or DEFAULT_GREETING, ctx.author
            )
        )

    @commands.hybrid_group(brief="Configure random welcome messages")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def welcome(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @welcome.command(name="channel", brief="Show or set the welcome channel")
    @configuration_command("manage_guild")
    async def welcome_channel(
        self, ctx: Context, channel: Optional[TextChannel] = None
    ):
        if channel is not None:
            await self.messages.set_channel(ctx.guild.id, channel.id)
            warning = await self._welcome_delivery_warning(ctx.guild.id, channel.id)
            return await ctx.send(
                f"Set the welcome channel to {channel.mention}{warning}"
            )
        settings = await self.messages.read(ctx.guild.id)
        await ctx.send(
            f"Welcome channel: <#{settings.channel_id}>"
            if settings.channel_id
            else "No welcome channel set"
        )

    @welcome.command(name="disable", brief="Disable welcome messages")
    @configuration_command("manage_guild")
    async def welcome_disable(self, ctx: Context):
        await self.messages.set_channel(ctx.guild.id, None)
        await ctx.send("Disabled welcome messages")

    @welcome.command(name="message", brief="Add a welcome message")
    @configuration_command("manage_guild")
    async def welcome_message(self, ctx: Context, message: str):
        added = await self.messages.add(ctx.guild.id, (message,))
        text = "Message added" if added else "Message already exists"
        if added:
            settings = await self.messages.read(ctx.guild.id)
            text += await self._welcome_delivery_warning(
                ctx.guild.id, settings.channel_id
            )
        await ctx.send(text)

    async def _welcome_delivery_warning(self, guild_id, channel_id):
        """A delivery advisory must not hide a successful configuration save."""
        if channel_id is None:
            return "\nWelcome delivery is currently disabled"
        try:
            can_send = await self.discord.can_send_messages(guild_id, channel_id)
        except (HTTPException, OSError, TimeoutError):
            return "\nI couldn't verify delivery permissions in the assigned channel right now"
        if can_send:
            return ""
        return "\nI don't have permissions to send messages in the assigned channel right now"

    @welcome.command(name="add_urls", brief="Import URLs from channel history")
    @configuration_command("manage_guild")
    async def welcome_add_urls(
        self, ctx: Context, channel: TextChannel, include_attachments: bool = True
    ):
        count, total = await self.import_urls.execute(
            ctx.guild.id, channel.id, include_attachments
        )
        await ctx.send(
            f"{count} messages added; {total - count} already saved"
            if total
            else "No urls found"
        )

    @welcome.command(
        name="remove_urls", brief="Remove welcome URLs found in channel history"
    )
    @configuration_command("manage_guild")
    async def welcome_remove_urls(
        self, ctx: Context, channel: TextChannel, include_attachments: bool = True
    ):
        count, total = await self.import_urls.execute(
            ctx.guild.id, channel.id, include_attachments, remove=True
        )
        await ctx.send(f"{count} messages removed from {total} source URLs")

    @welcome.command(name="clear", brief="Clear all welcome messages")
    @configuration_command("manage_guild")
    async def welcome_clear(self, ctx: Context):
        await self.messages.clear(ctx.guild.id)
        await ctx.send("Cleared all welcome messages")

    @welcome.command(name="remove", brief="Remove a welcome message by ID or content")
    @configuration_command("manage_guild")
    async def welcome_remove(
        self,
        ctx: Context,
        message_id: Optional[int] = None,
        message_content: Optional[str] = None,
    ):
        count = await self.messages.remove(ctx.guild.id, message_id, message_content)
        await ctx.send(
            "Message removed"
            if count
            else "Message not found. Use `welcome list` to see message IDs"
        )

    @welcome.command(name="list", brief="List welcome messages")
    @configuration_command("manage_guild")
    async def welcome_list(self, ctx: Context):
        settings = await self.messages.read(ctx.guild.id)
        if not settings.messages:
            return await ctx.send("No welcome messages set")
        view = MessagesList(ctx, settings.messages)
        view.message = await ctx.send(
            embed=view.create_embed(view.current_chunk), view=view
        )

    @welcome.command(name="preview", brief="Preview a random welcome message")
    @configuration_command("manage_guild")
    async def welcome_preview(self, ctx: Context):
        settings = await self.messages.read(ctx.guild.id)
        await ctx.send(
            random.choice(settings.messages).content
            if settings.messages
            else "No welcome messages"
        )

    @commands.hybrid_group(brief="Manage auto roles", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @autorole.command(name="add", brief="Add an automatic role")
    @configuration_command("manage_roles")
    async def add_role(self, ctx: Context, role: Role):
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            raise OnboardingInputError(
                "You can only configure auto roles below your highest role"
            )
        added = await self.roles.add(ctx.guild.id, role.id)
        await ctx.send(
            f"{role.mention} added to auto role list"
            if added
            else "Role already exists in auto role list"
        )

    @autorole.command(name="apply_all", brief="Apply auto roles to existing members")
    @configuration_command("manage_roles")
    async def apply_all(self, ctx: Context, include_bots: bool = False):
        result = await self.assign_roles.execute(
            ctx.guild.id,
            tuple(member_info(member) for member in ctx.guild.members),
            include_bots,
        )
        for member_id, error in result.failures:
            self.bot.logger.error(
                "Auto role assignment failed guild_id=%s member_id=%s",
                ctx.guild.id,
                member_id,
                exc_info=error,
            )
        await ctx.send(assignment_summary(result))

    @autorole.command(name="remove", brief="Remove an automatic role")
    @configuration_command("manage_roles")
    async def remove_role(self, ctx: Context, role: Role):
        count = await self.roles.remove(ctx.guild.id, (role.id,))
        await ctx.send(
            "Role removed from auto role list"
            if count
            else "Role not found in auto role list"
        )

    @autorole.command(name="list", brief="List automatic roles")
    @configuration_command("manage_roles")
    async def list_roles(self, ctx: Context):
        roles = await self.roles.available(ctx.guild.id)
        if not roles:
            return await ctx.send("No auto roles set for this server")
        await ctx.send(embed=role_embed(roles))

    @autorole.command(brief="Remove all automatic roles")
    @configuration_command("manage_roles")
    async def remove_all(self, ctx: Context):
        await self.roles.clear(ctx.guild.id)
        await ctx.send("All auto roles removed")

    @Cog.listener()
    async def on_member_join(self, member: Member):
        discord = DiscordOnboarding(self.bot, member)
        roles = ApplyAutoRoles(ConfigureAutoRoles(self.repository, discord), discord)
        actions = ConfiguredJoinActions(
            member.guild.id,
            member_info(member),
            self.repository,
            discord,
            roles,
            random.choice,
        )
        failures = await HandleMemberJoin(actions).execute()
        for failure in failures:
            self.bot.logger.error(
                "Member join %s failed guild_id=%s member_id=%s",
                failure.action.value,
                member.guild.id,
                member.id,
                exc_info=(type(failure.error), failure.error, failure.traceback),
            )


async def setup(bot):
    await bot.add_cog(MemberOnboardingCog(bot))
