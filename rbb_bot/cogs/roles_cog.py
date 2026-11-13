import json
import re
from typing import Literal

from discord import Embed, Role
from discord.ext import commands
from discord.ext.commands import Cog, Context

from rbb_bot.application.custom_roles.configure import ConfigureCustomRoles
from rbb_bot.application.custom_roles.contracts import (
    CustomRoleRefused,
    RoleDeletionFailed,
)
from rbb_bot.application.custom_roles.manage_roles import (
    CreateCustomRole,
    DeleteCustomRoles,
    RemoveCustomRole,
)
from rbb_bot.infrastructure.custom_roles.discord_guild import DiscordCustomRoles
from rbb_bot.infrastructure.custom_roles.repository import (
    TortoiseCustomRoleRepository,
)
from rbb_bot.views.custom_roles import ColorsList, refusal_reply

from rbb_bot.settings.const import FilePaths


class RolesCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.repository = TortoiseCustomRoleRepository()
        self.configure = ConfigureCustomRoles(self.repository)
        with open(FilePaths.COLORS_FILE, "r", encoding="utf-8") as f:
            self.colors_dict = json.load(f)

        # Maps color names to hex codes
        self.colors_map = dict()
        for _, color in self.colors_dict.items():
            for name, hex_code in color.items():
                self.colors_map[name] = hex_code

    async def cog_load(self):
        self.bot.logger.debug("RolesCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("RolesCog unloaded!")

    @commands.hybrid_group(brief="Manage custom roles for this server")
    @commands.guild_only()
    async def roles(self, ctx):
        """
        Manage custom roles for this server

        When enabled, users can create custom roles for themselves.
        Only roles recorded as created by this bot can be removed, and only when
        they are not manually assigned to more than one user.
        I will need `manage roles` permission for this.
        The role assigned to me will also need to be positioned above other users' roles.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @roles.command(brief="help")
    @commands.guild_only()
    async def help(self, ctx: Context):
        """
        Information about this command
        """
        info = (
            "When enabled, users can create custom roles for themselves. "
            "Only roles recorded as created by this bot can be removed, and only when "
            "they are not manually assigned to more than one user. "
        )
        embed = Embed(title="Roles Help", description=info)
        embed.add_field(name="Required Permissions", value="Manage Roles")
        embed.add_field(
            name="Additional Requirements",
            value="My role position above other members",
        )
        await ctx.send(embed=embed)

    @roles.command(brief="Enable custom roles for this server")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def enable(self, ctx: Context, enabled: bool):
        """
        Enable custom roles for this server

        Parameters
        ----------
        enabled : bool
            Whether to enable or disable custom roles (True/False)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        await self.configure.enable(ctx.guild.id, enabled)
        await ctx.send(
            f"Custom roles are now {'enabled' if enabled else 'disabled'}. "
            f"I will need `manage roles` permission. "
            "The role assigned to me will also need to be above all other members."
        )

    @roles.command(name="max", brief="Set maximum number of custom roles per user")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def max_(self, ctx: Context, max_roles: Literal[1, 2, 3, 4, 5]):
        """
        Set maximum number of custom roles per user


        Parameters
        ----------
        max_roles : Literal[1, 2, 3, 4, 5]
            Maximum number of custom roles per user (1-5) (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        try:
            await self.configure.set_max_roles(ctx.guild.id, max_roles)
        except CustomRoleRefused as refusal:
            return await ctx.send(**refusal_reply(refusal, ctx.prefix))
        await ctx.send(f"Maximum number of custom roles per user is now {max_roles}")

    @roles.command(brief="Remove unused roles")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def prune(self, ctx: Context):
        """
        Remove unused roles
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        deleted = await self._cleanup(ctx.guild, unused_only=True)
        await ctx.send(f"Deleted {deleted} unused bot-created roles")

    @roles.command(brief="Clear bot-created custom roles")
    @commands.guild_only()
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.has_permissions(manage_roles=True)
    async def clear(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        prompt = (
            "Delete all recorded bot-created custom roles that are unused or held only by their owner? "
            "Shared roles and roles without ownership records will be preserved. This cannot be undone."
        )
        if not await self.bot.get_confirmation(ctx, prompt):
            return await ctx.send("Cancelled")
        deleted = await self._cleanup(ctx.guild)
        await ctx.send(f"Deleted {deleted} bot-created roles")

    async def _cleanup(self, guild, **options):
        cleanup = await DeleteCustomRoles(
            self.repository, DiscordCustomRoles(guild)
        ).execute(**options)
        self._log_failures(guild.id, cleanup)
        return cleanup.deleted

    def _log_failures(self, guild_id, cleanup):
        for failure in cleanup.failures:
            self.bot.logger.error(
                "Custom role deletion failed guild_id=%s role_id=%s",
                guild_id,
                failure.role_id,
                exc_info=failure,
            )

    def parse_color_input(self, color_input: str) -> int | None:
        """
        Parse color string input by the user and return its RGB value

        Return None if the color is invalid
        """
        if re.match(r"^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$", color_input):
            return int(color_input.replace("#", ""), 16)
        color_input = color_input.strip().lower()
        for name, hex_code in self.colors_map.items():
            if color_input == name.lower():
                return int(hex_code[1:], 16)

    @roles.command(brief="Show a list of available colors")
    @commands.guild_only()
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def colors(self, ctx: Context):
        """
        Show a list of available colors
        """
        view = ColorsList(ctx, list(self.colors_map.items()), chunk_size=15)
        view.embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=view.embed, view=view)

    @roles.command(brief="Create a custom role for yourself")
    @commands.guild_only()
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.member, wait=False)
    async def add(self, ctx: Context, color: str, *, name: str):
        """
        Create a custom role for yourself

        Parameters
        ----------
        color: str
            Hex color code for the role or a valid color name (Required)
        name: str
            Name for the role. This can be up to 100 characters long. (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild = DiscordCustomRoles(ctx.guild, ctx.author)
        try:
            role_id = await CreateCustomRole(self.repository, guild).execute(
                ctx.author.id, name, self.parse_color_input(color)
            )
        except CustomRoleRefused as refusal:
            return await ctx.send(**refusal_reply(refusal, ctx.prefix))
        await ctx.send(f"Created role <@&{role_id}>")

        if not await guild.place_on_top(role_id):
            await ctx.send(
                "I don't have permission to reposition roles. "
                "Please move my role above others so I can do this in the future."
            )

    @roles.command(brief="Remove a custom role")
    @commands.guild_only()
    async def remove(self, ctx: Context, *, role: Role):
        """
        Remove a custom role

        Parameters
        ----------
        role: Role
            The role to remove (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        try:
            await RemoveCustomRole(
                self.repository, DiscordCustomRoles(ctx.guild, ctx.author)
            ).execute(ctx.author.id, role.id)
        except CustomRoleRefused as refusal:
            return await ctx.send(**refusal_reply(refusal, ctx.prefix))
        except RoleDeletionFailed as failure:
            # Re-raise Discord's own error so the shared command error handler can
            # show the member why Discord refused (it reports Forbidden reasons).
            raise failure.__cause__ from None
        await ctx.send("Deleted role")

    @Cog.listener()
    async def on_member_remove(self, member):
        cleanup = await DeleteCustomRoles(
            self.repository, DiscordCustomRoles(member.guild)
        ).departed(member.id)
        if cleanup is not None:
            self._log_failures(member.guild.id, cleanup)


async def setup(bot):
    await bot.add_cog(RolesCog(bot))
