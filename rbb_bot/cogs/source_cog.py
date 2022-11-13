from discord.ext import commands
from discord.ext.commands import Cog, Context


class SourceCog(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.logger.debug("SourceCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("SourceCog unloaded!")

    @commands.group(
        brief="This command will be back soon :)", invoke_without_command=True
    )
    async def source(self, ctx: Context):
        await ctx.send("This command will be back soon :)")


async def setup(bot):
    await bot.add_cog(SourceCog(bot))
