import json
import re
from typing import Literal

import discord
from discord import Color, Embed, Role
from discord.errors import Forbidden
from discord.ext import commands
from discord.ext.commands import Cog, Context
from models import Guild
from utils.views import ListView

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
        These roles will be deleted when the user removes them as long as
        they are not manually assigned to more than one user.
        I will need `manage roles` permission for this.
        The role assigned to me will also need to be positioned above other users' roles.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @roles.command(brief="help")
    async def help(self, ctx: Context):
        """
        Information about this command
        """
        info = (
            "When enabled, users can create unique custom roles for themselves. "
            "These roles will be deleted when the user removes them as long as "
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
    @commands.has_permissions(manage_roles=True)
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def prune(self, ctx: Context):
        """
        Remove unused roles
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        final_message = list()
        for role in ctx.guild.roles:
            if not role.members:
                try:
                    await role.delete()
                    final_message.append(f"Deleted role {role.name}")
                except Forbidden as e:
                    final_message.append(
                        f"Error deleting role {role.mention}. I may not have permission to remove it"
                    )
                    break
        if final_message:
            await ctx.send("\n".join(final_message))
        else:
            await ctx.send("No unused roles found")

    @roles.command(brief="Clear all unique roles belonging to users")
    @commands.cooldown(2, 5, commands.BucketType.user)
    @commands.has_permissions(manage_roles=True)
    async def clear(self, ctx: Context):
        """
        Clear all unique roles belonging to users
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        prompt = (
            "Are you sure you want to delete **all** unique roles belonging to users? "
            "Unique roles are roles that are assigned to a single user each. "
            "This may include roles created by others. **This action cannot be undone.** Bots will be unaffected."
        )
        if not (await self.bot.get_confirmation(ctx, prompt)):
            return await ctx.send("Cancelled")

        deleted_count = 0
        for role in [r for r in ctx.guild.roles if len(r.members) == 1]:
            if role.members[0].bot:
                continue
            try:
                await role.delete()
                deleted_count += 1
            except Forbidden as e:
                return await ctx.send(
                    f"Error deleting role {role.mention}. I may not have permission to remove it"
                )

        await ctx.send(f"Deleted {deleted_count} roles")

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
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def colors(self, ctx: Context):
        """
        Show a list of available colors
        """
        view = ColorsList(ctx, list(self.colors_map.items()), chunk_size=15)
        view.embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=view.embed, view=view)

    @roles.command(brief="Create a unique role for yourself")
    @commands.cooldown(2, 5, commands.BucketType.user)
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

        unique_roles = [
            r for r in ctx.guild.roles if r in ctx.author.roles and len(r.members) == 1
        ]
        if len(unique_roles) >= guild.max_custom_roles:
            to_send = (
                f"You already have {guild.max_custom_roles} unique roles. "
                f"{' '.join(r.mention for r in unique_roles)}. "
                f"You can remove one of these roles with `{ctx.prefix}roles remove <role>`"
            )
            if guild.max_custom_roles < 5:
                to_send = (
                    f"{to_send}\nAlternatively you can ask someone with `manage roles` "
                    "permission to increase the "
                    f"maximum number of unique roles per user with `{ctx.prefix}roles max <number>`"
                )
            return await ctx.send(to_send)

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

        if role not in ctx.author.roles:
            return await ctx.send(
                "You do not have this role. You can only remove roles assigned to you and no one else"
            )

        if len(role.members) > 1:
            return await ctx.send(
                "This role is assigned to multiple users. "
                "It cannot be deleted automatically."
            )

        await role.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
        await ctx.send(f"Deleted role")

    @Cog.listener()
    async def on_member_leave(self, member):
        guild, _ = await Guild.get_or_create(id=member.guild.id)
        if not guild.custom_roles_enabled:
            return

        for role in member.roles:
            if len(role.members) > 1:
                continue
            try:
                await role.delete(reason=f"Deleted because {member} left the server")
            except discord.Forbidden:
                pass


async def setup(bot):
    await bot.add_cog(RolesCog(bot))
