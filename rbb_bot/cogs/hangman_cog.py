import random

from discord import ButtonStyle, Interaction
from discord.ext import commands
from discord.ext.commands import Cog, Context
from discord.ui import Button, View

from rbb_bot.settings.const import FilePaths


class LetterButton(Button):
    def __init__(self, letter: str, *args, **kwargs):
        super().__init__(label=letter, *args, **kwargs)
        self.letter = letter

    async def callback(self, interaction: Interaction):
        if self.style == ButtonStyle.blurple:
            username = interaction.user.name
            self.disabled = True
            if self.letter in self.view.word:
                self.style = ButtonStyle.green
            else:
                self.style = ButtonStyle.red

            if username not in self.view.guesses:
                self.view.guesses[username] = [self.letter]
            else:
                self.view.guesses[username].append(self.letter)
            if self.letter not in self.view.word:
                self.view.wrong_guesses += 1
            await self.view.update_view()
        if self.view.game_over:
            self.view.end_game()
            self.view.stop()
        await interaction.response.edit_message(view=self.view)


class HangmanView(View):
    BLANK = "-"

    def __init__(self, ctx: Context, word: str, timeout=60.0):
        self.ctx = ctx
        self.word = word.upper()
        self.guesses = {}
        self.message = None
        self.wrong_guesses = 0
        self.max_wrong_guesses = 6
        self.game_over = False
        super().__init__(timeout=timeout)
        self.create_buttons()

    async def update_view(self):
        message = await self.create_message()
        await self.message.edit(content=message, view=self)

    async def create_message(self):
        """
        Create a message to display the current state of the game
        """
        message = ""
        for username in self.guesses:
            message += (
                f"**{username}** guessed {','.join(self.guesses[username])} "
                f"`{self.correct_percentage(username):.1f}%` correct guesses. "
                f"`{self.guessed_percentage(username):.1f}%` of the word guessed\n"
            )

        displayed_word = ""
        for letter in self.word:
            if letter in self.guessed:
                displayed_word += letter
            else:
                displayed_word += self.BLANK
        message += f"`{displayed_word}`\n"

        if self.BLANK not in displayed_word:
            message += f"You won! The word was {self.word}"
            self.game_over = True
        elif self.wrong_guesses >= self.max_wrong_guesses:
            message += f"You lost! The word was {self.word}"
            self.game_over = True
        message = (
            f"{message} Guesses left: {self.max_wrong_guesses - self.wrong_guesses}"
        )
        return message

    @property
    def guessed(self):
        """
        Return a list of all the letters that have been guessed
        """
        return [
            letter for username in self.guesses for letter in self.guesses[username]
        ]

    def correct_percentage(self, username: str) -> float:
        correct_guesses = sum(
            [1 for guess in self.guesses[username] if guess in self.word]
        )
        return (correct_guesses / len(self.guesses[username])) * 100

    def guessed_percentage(self, username: str) -> float:
        correct_guesses = sum(
            [1 for guess in self.guesses[username] if guess in self.word]
        )
        return (correct_guesses / len(set(self.word))) * 100

    def create_buttons(self):
        # Skipping Z because of the 25 components limit
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXY"
        for letter in alphabet:
            self.add_item(LetterButton(letter, style=ButtonStyle.blurple))

    def end_game(self):
        for child in self.children:
            child.disabled = True

    async def on_timeout(self):
        self.end_game()
        self.game_over = True
        new_content = f"{(await self.create_message())}\nGame timed out"
        await self.message.edit(content=new_content, view=self)


class HangmanCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        with open(FilePaths.WORDS_FILE, "r") as f:
            # z will not be used because of the 25 components limit
            self.words = [word for word in f.read().splitlines() if "z" not in word]

        # Channel ids to hangman views mapping. This is used to prevent multiple games in the same channel
        self.ongoing_games = dict()

    async def cog_load(self):
        self.bot.logger.debug("HangmanCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("HangmanCog unloaded!")

    @commands.hybrid_group(brief="Play hangman")
    async def hangman(self, ctx: Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @hangman.command(name="start", brief="Start a new game")
    async def start_game(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        word = random.choice(self.words)
        view = HangmanView(ctx, word)
        if (cid := ctx.channel.id) in self.ongoing_games and not self.ongoing_games[
            cid
        ].game_over:
            return await ctx.send("There is already a game in this channel")
        self.ongoing_games[cid] = view
        view.message = await ctx.send(content=(await view.create_message()), view=view)

    @hangman.command(name="end", brief="End the current game")
    @commands.has_permissions(manage_messages=True)
    async def end_game(self, ctx: Context):
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if (cid := ctx.channel.id) in self.ongoing_games:
            self.ongoing_games[cid].end_game()
            await self.ongoing_games[cid].update_view()
            del self.ongoing_games[cid]
            await ctx.send("Game ended")
        else:
            await ctx.send("There is no game in this channel")


async def setup(bot):
    await bot.add_cog(HangmanCog(bot))
