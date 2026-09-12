from dataclasses import dataclass, field


@dataclass
class HangmanGame:
    word: str
    guesses: dict[int, list[str]] = field(default_factory=dict)
    players: dict[int, str] = field(default_factory=dict)
    stopped: str | None = None
    max_wrong_guesses: int = 6

    @property
    def guessed(self):
        return {letter for guesses in self.guesses.values() for letter in guesses}

    @property
    def wrong_guesses(self):
        return len(self.guessed - set(self.word))

    @property
    def won(self):
        return set(self.word) <= self.guessed

    @property
    def over(self):
        return (
            self.stopped is not None
            or self.won
            or self.wrong_guesses >= self.max_wrong_guesses
        )

    def guess(self, player_id, name, letter):
        """Each letter can affect the shared game once, even when multiple players click it."""
        if self.over or letter in self.guessed:
            return False
        self.players[player_id] = name
        self.guesses.setdefault(player_id, []).append(letter)
        return True
