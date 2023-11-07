import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context

from rbb_bot.tweetmeme.memegen import TweetMeme
from rbb_bot.utils.decorators import log_command


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
        async with ctx.typing():
            irene_meme = TweetMeme()
            meme_file = await irene_meme.create_meme(text)
            await ctx.send(file=discord.File(meme_file))
        try:
            meme_file.unlink(missing_ok=True)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(MemeCog(bot))
