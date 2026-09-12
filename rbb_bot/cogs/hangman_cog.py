import asyncio
import random

from discord.ext import commands
from discord.ext.commands import Cog, Context
from rbb_bot.settings.const import FilePaths
from rbb_bot.views.hangman import HangmanView


class HangmanCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        # The button layout supports 25 letters; validate the word file at this boundary.
        self.words = [
            word.strip().upper()
            for word in FilePaths.WORDS_FILE.read_text().splitlines()
            if word.strip()
            and set(word.strip().upper()) <= set("ABCDEFGHIJKLMNOPQRSTUVWXY")
        ]
        self.ongoing_games = {}

    async def cog_unload(self):
        views = tuple(self.ongoing_games.values())
        results = await asyncio.gather(
            *(view.finish("Game stopped") for view in views), return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                self.bot.logger.error(
                    "Could not close hangman message", exc_info=result
                )
        self.ongoing_games.clear()

    @commands.hybrid_group(brief="Play hangman")
    async def hangman(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    def finished(self, channel_id, view):
        if self.ongoing_games.get(channel_id) is view:
            del self.ongoing_games[channel_id]

    @hangman.command(name="start", brief="Start a new game")
    async def start_game(self, ctx: Context):
        await ctx.defer()
        channel_id = ctx.channel.id
        if channel_id in self.ongoing_games:
            return await ctx.send("There is already a game in this channel")
        view = HangmanView(
            random.choice(self.words), lambda view: self.finished(channel_id, view)
        )
        self.ongoing_games[channel_id] = view
        try:
            view.message = await ctx.send(content=view.create_message(), view=view)
        except Exception:
            view.close_game()
            raise

    @hangman.command(name="end", brief="End the current game")
    @commands.has_permissions(manage_messages=True)
    async def end_game(self, ctx: Context):
        await ctx.defer()
        view = self.ongoing_games.get(ctx.channel.id)
        if view is None:
            return await ctx.send("There is no game in this channel")
        await view.finish("Game ended")
        await ctx.send("Game ended")


async def setup(bot):
    await bot.add_cog(HangmanCog(bot))
