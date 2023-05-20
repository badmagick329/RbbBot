from typing import List

from discord import Embed
from discord.ext import commands
from discord.ext.commands import Cog, Context
from discord.utils import format_dt
from models import BotIssue, BotUpdate
from utils.views import ListView

from rbb_bot.utils.decorators import log_command


class UpdatesView(ListView):
    def create_embed(self, items: List[BotIssue | BotUpdate]) -> Embed:
        header = "Know Issues" if isinstance(items[0], BotIssue) else "Updates"
        if len(self.view_chunks) > 1:
            page_header = f"\nPage {self.current_page + 1} of {len(self.view_chunks)}"
        else:
            page_header = ""
        embed = Embed(title=f"{header}{page_header}")

        for item in items:
            embed.add_field(
                name=format_dt(item.created_at, "f"),
                value=item.message,
                inline=False,
            )
        return embed


class UpdatesCog(Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.logger.debug("BotCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("BotCog unloaded!")

    @commands.hybrid_group(name="bot", brief="View bot updates and known issues")
    async def updates_group(self, ctx: Context):
        """
        View bot updates and known issues
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @updates_group.command(name="updates", brief="View bot updates")
    @log_command(command_name="bot updates")
    async def updates_cmd(self, ctx: Context):
        """
        View bot updates
        """
        updates = await BotUpdate.all().order_by("-created_at")
        if not updates:
            return await ctx.send("No new updates at this time.")
        view = UpdatesView(ctx, updates)
        embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=embed, view=view)
        return view.message

    @updates_group.command(name="issues", brief="View bot known issues")
    @log_command(command_name="bot issues")
    async def issues_cmd(self, ctx: Context):
        """
        View bot known issues
        """
        issues = await BotIssue.all().order_by("-created_at")
        if not issues:
            return await ctx.send("No known issues at this time.")
        view = UpdatesView(ctx, issues)
        embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=embed, view=view)
        return view.message


async def setup(bot):
    await bot.add_cog(UpdatesCog(bot))
