import json
import re
from typing import Literal

import discord
from discord import Color, Embed, Role
from discord.ext import commands
from discord.ext.commands import Cog, Context
from rbb_bot.models import Guild
from rbb_bot.infrastructure.custom_roles.repository import CustomRoleRepository
from rbb_bot.utils.views import ListView

from rbb_bot.settings.const import FilePaths


class ColorsList(ListView):
    def create_embed(self, colors: list[tuple[str, str]]) -> Embed:
        embed = Embed(title=f"Page {self.current_page + 1} of {len(self.view_chunks)}")
        for color in colors:
            name, hex_code = color
            embed.add_field(name=name, value=hex_code, inline=True)
        embed.set_footer(text=f"Source: https://htmlcolorcodes.com/color-names/")
        return embed


class RolesCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ownership = CustomRoleRepository()
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

    @commands.hybrid_group(brief="Manage unique roles for this server")
    @commands.guild_only()
    async def roles(self, ctx):
        """
        Manage unique roles for this server

        When enabled, users can create unique custom roles for themselves.
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
            "When enabled, users can create unique custom roles for themselves. "
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

    @roles.command(brief="Enable unique roles for this server")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def enable(self, ctx: Context, enabled: bool):
        """
        Enable unique roles for this server

        Parameters
        ----------
        enabled : bool
            Whether to enable or disable unique roles (True/False)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        guild.custom_roles_enabled = enabled
        await guild.save()
        await ctx.send(
            f"Custom roles are now {'enabled' if enabled else 'disabled'}. "
            f"I will need `manage roles` permission. "
            "The role assigned to me will also need to be above all other members."
        )

    @roles.command(name="max", brief="Set maximum number of unique roles per user")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def max_(self, ctx: Context, max_roles: Literal[1, 2, 3, 4, 5]):
        """
        Set maximum number of unique roles per user


        Parameters
        ----------
        max_roles : Literal[1, 2, 3, 4, 5]
            Maximum number of unique roles per user (1-5) (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if max_roles < 1 or max_roles > 5:
            return await ctx.send("Max roles must be between 1 and 5")

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        guild.max_custom_roles = max_roles
        await guild.save()
        await ctx.send(f"Maximum number of unique roles per user is now {max_roles}")

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

        deleted = await self._delete_tracked_roles(ctx.guild, unused_only=True)
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
        deleted = await self._delete_tracked_roles(ctx.guild)
        await ctx.send(f"Deleted {deleted} bot-created roles")

    async def _tracked_roles(self, guild, owner_id=None):
        # Role.members is derived from the member cache, not a Discord API count.
        if not guild.chunked:
            await guild.chunk()
        records = await self.ownership.list(guild.id, owner_id)
        roles = {role.id: role for role in guild.roles}
        if any(record.role_id not in roles for record in records):
            roles = {role.id: role for role in await guild.fetch_roles()}
        result = []
        for record in records:
            role = roles.get(record.role_id)
            if role is None:
                await self.ownership.forget(guild.id, record.role_id)
            else:
                result.append((record, role))
        return result

    async def _delete_recorded_role(self, guild, role):
        try:
            await role.delete(reason="Removing recorded bot-created custom role")
        except discord.NotFound:
            pass
        await self.ownership.forget(guild.id, role.id)

    async def _delete_tracked_roles(self, guild, owner_id=None, unused_only=False):
        deleted = 0
        for record, role in await self._tracked_roles(guild, owner_id):
            if not record.permits_deletion(
                (member.id for member in role.members),
                managed=role.managed,
                default=role.is_default(),
            ):
                continue
            if unused_only and role.members:
                continue
            try:
                await self._delete_recorded_role(guild, role)
                deleted += 1
            except discord.HTTPException:
                # Preserve ownership so a later prune can retry failed deletions.
                self.bot.logger.exception(
                    "Custom role deletion failed guild_id=%s role_id=%s",
                    guild.id,
                    role.id,
                )
        return deleted

    def parse_color_input(self, color_input: str):
        """
        Parse color string input by the user and return a discord Color object

        Return None if the color is invalid
        """
        if re.match(r"^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$", color_input):
            return Color(int(color_input.replace("#", ""), 16))
        color_input = color_input.strip().lower()
        for name, hex_code in self.colors_map.items():
            if color_input == name.lower():
                return discord.Color(int(hex_code[1:], 16))

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

    @roles.command(brief="Create a unique role for yourself")
    @commands.guild_only()
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.member, wait=False)
    async def add(self, ctx: Context, color: str, *, name: str):
        """
        Create a unique role for yourself

        Parameters
        ----------
        color: str
            Hex color code for the role or a valid color name (Required)
        name: str
            Name for the role. This can be up to 100 characters long. (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if not guild.custom_roles_enabled:
            return await ctx.send("Custom roles are not enabled for this server")

        tracked = await self._tracked_roles(ctx.guild, ctx.author.id)
        # Count untracked sole-holder roles too: erasing ownership data must not
        # let a member bypass the server's role limit.
        unique_ids = {record.role_id for record, _ in tracked} | {
            role.id for role in ctx.author.roles if len(role.members) == 1
        }
        if len(unique_ids) >= guild.max_custom_roles:
            return await ctx.send(
                f"You already have {guild.max_custom_roles} unique roles. Remove one or ask a server administrator for help."
            )

        name = name.strip()
        if len(name) > 100:
            return await ctx.send(
                "Role name is too long. It must be 100 characters or less."
            )
        if name in [r.name for r in ctx.guild.roles]:
            return await ctx.send("Role name is already in use")

        discord_color = self.parse_color_input(color)

        if not discord_color:
            embed = Embed(
                title="Color must be a hex code or a valid color name",
                description="You can use google's color picker to get a hex code. "
                f"Alternatively you can use the `{ctx.prefix}roles colors` to "
                "see a list of valid color names",
            )
            embed.add_field(
                name="Hex color picker",
                value="https://www.google.com/search?q=color+picker",
            )
            return await ctx.send(embed=embed)

        role = await ctx.guild.create_role(
            name=name,
            color=discord_color,
            reason=f"Created by {ctx.author} ({ctx.author.id})",
        )

        try:
            await self.ownership.record(ctx.guild.id, ctx.author.id, role.id)
        except Exception:
            await role.delete(reason="Could not record custom role ownership")
            raise
        await ctx.author.add_roles(role)
        await ctx.send(f"Created role {role.mention}")

        if len(ctx.author.roles) == 1:
            return

        try:
            top_pos = ctx.author.top_role.position
            await ctx.author.top_role.edit(position=top_pos - 1)
            await role.edit(position=top_pos)
        except discord.HTTPException as e:
            await ctx.send(
                "I don't have permission to reposition roles. "
                "Please move my role above others so I can do this in the future."
            )

    @roles.command(brief="Remove a unique role")
    @commands.guild_only()
    async def remove(self, ctx: Context, *, role: Role):
        """
        Remove a unique role

        Parameters
        ----------
        role: Role
            The role to remove (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        guild, _ = await Guild.get_or_create(id=ctx.guild.id)
        if not guild.custom_roles_enabled:
            return await ctx.send("Custom roles are not enabled for this server")

        tracked = await self._tracked_roles(ctx.guild, ctx.author.id)
        ownership = next(
            (record for record, _ in tracked if record.role_id == role.id), None
        )
        if ownership is None:
            return await ctx.send(
                "You can only remove bot-created roles recorded as yours"
            )
        if not ownership.permits_deletion(
            (member.id for member in role.members),
            managed=role.managed,
            default=role.is_default(),
        ):
            return await ctx.send(
                "This role is shared or managed and cannot be deleted automatically"
            )
        await self._delete_recorded_role(ctx.guild, role)
        await ctx.send("Deleted role")

    @Cog.listener()
    async def on_member_remove(self, member):
        guild = await Guild.get_or_none(id=member.guild.id)
        if guild is not None and guild.custom_roles_enabled:
            await self._delete_tracked_roles(member.guild, owner_id=member.id)


async def setup(bot):
    await bot.add_cog(RolesCog(bot))
