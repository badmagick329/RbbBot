from pathlib import Path
from typing import Protocol

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context

from rbb_bot.memegifs.memegen import ElijahTerrific, IreneTweeting
from rbb_bot.utils.decorators import log_command


class MemeGenerator(Protocol):
    async def create(self, text: str) -> Path:
        ...


class MemeCog(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.logger.debug("MemeCog Cog loaded!")

    async def cog_unload(self) -> None:
        self.bot.logger.debug("MemeCog Cog unloaded!")

    @commands.hybrid_group(
        brief="Generate memes",
        invoke_without_command=True,
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def meme(self, ctx: Context, *args, **kwargs):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @meme.command(brief="Tweet meme")
    @log_command("tweet")
    async def tweet(self, ctx: commands.Context, *, text: str):
        if text.strip() == "":
            return await ctx.send("No text provided")
        try:
            irene_tweeting = IreneTweeting()
            await self.create_and_send(ctx, irene_tweeting, text.upper())
        except Exception as e:
            self.logger.error(f"Error in meme tweet. {e}", exc_info=e)
            return await ctx.send("Something went wrong 😕")

    @meme.command(brief="Elijah meme")
    @log_command("elijah")
    async def elijah(self, ctx: commands.Context, *, text: str):
        if text.strip() == "":
            return await ctx.send("No text provided")
        try:
            elijah = ElijahTerrific()
            await self.create_and_send(ctx, elijah, text.upper())
        except Exception as e:
            self.bot.logger.error(f"Error in meme elijah. {e}", exc_info=e)
            return await ctx.send("Something went wrong 😕")

    async def create_and_send(
        self, ctx: Context, memegen: MemeGenerator, text: str
    ):
        async with ctx.typing():
            meme_file = await memegen.create(text)
            await ctx.send(file=discord.File(meme_file))
        try:
            meme_file.unlink(missing_ok=True)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(MemeCog(bot))
