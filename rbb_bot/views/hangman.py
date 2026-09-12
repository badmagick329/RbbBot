import asyncio

import discord
from discord import ButtonStyle
from discord.ui import Button, View
from rbb_bot.domain.hangman import HangmanGame


class LetterButton(Button):
    def __init__(self, letter):
        super().__init__(label=letter, style=ButtonStyle.blurple)
        self.letter = letter

    async def callback(self, interaction):
        async with self.view.lock:
            game = self.view.game
            game.guess(interaction.user.id, interaction.user.name, self.letter)
            self.view.refresh_buttons()
            try:
                await interaction.response.edit_message(
                    content=self.view.create_message(), view=self.view
                )
            finally:
                if game.over:
                    self.view.close_game()


class HangmanView(View):
    def __init__(self, word, on_finished, timeout=60):
        super().__init__(timeout=timeout)
        self.game = HangmanGame(word.upper())
        self.message = None
        self.lock = asyncio.Lock()
        self.on_finished = on_finished
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXY":
            self.add_item(LetterButton(letter))

    def refresh_buttons(self):
        for button in self.children:
            guessed = button.letter in self.game.guessed
            button.disabled = self.game.over or guessed
            if guessed:
                button.style = (
                    ButtonStyle.green
                    if button.letter in self.game.word
                    else ButtonStyle.red
                )

    def create_message(self):
        game = self.game
        rows = []
        for player_id, guesses in game.guesses.items():
            correct = sum(letter in game.word for letter in guesses)
            # Keep all 25 possible players within Discord's message limit.
            name = game.players[player_id]
            if len(name) > 16:
                name = name[:15] + "…"
            name = discord.utils.escape_markdown(name)
            rows.append(
                f"**{name}**: {','.join(guesses)} · {100 * correct / len(guesses):.1f}% correct · {100 * correct / len(set(game.word)):.1f}% of word"
            )
        rows.append(
            "`"
            + "".join(letter if letter in game.guessed else "-" for letter in game.word)
            + "`"
        )
        if game.stopped:
            rows.append(f"{game.stopped}. The word was {game.word}")
        elif game.won:
            rows.append(f"You won! The word was {game.word}")
        elif game.over:
            rows.append(f"You lost! The word was {game.word}")
        rows.append(f"Guesses left: {game.max_wrong_guesses - game.wrong_guesses}")
        return "\n".join(rows)

    def close_game(self):
        self.stop()
        self.on_finished(self)

    async def finish(self, reason):
        async with self.lock:
            self.game.stopped = reason
            self.refresh_buttons()
            try:
                if self.message is not None:
                    await self.message.edit(content=self.create_message(), view=self)
            finally:
                self.close_game()

    async def on_timeout(self):
        await self.finish("Game timed out")
