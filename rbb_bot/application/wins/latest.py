import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from time import monotonic
from typing import Callable, Protocol


@dataclass(frozen=True)
class RecordedWin:
    id: int
    date: date
    show: str
    song_id: int
    song: str
    artist_id: int
    artist_slug: str
    artist: str


class WinsUnavailable(Exception):
    """An expected upstream failure, safe for presentation to translate."""


class InvalidArtist(ValueError):
    pass


def normalize_artist(artist: str | None) -> str | None:
    if artist is None:
        return None
    artist = artist.strip()
    if (
        not artist
        or len(artist) > 100
        or any(ord(char) < 32 or ord(char) == 127 for char in artist)
    ):
        raise InvalidArtist("Enter an artist name or alias of 1–100 characters.")
    return artist


def korean_today() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


class WinsSource(Protocol):
    async def fetch(
        self, artist: str | None, cutoff: date
    ) -> tuple[RecordedWin, ...]: ...


class LatestWins:
    """Bound cached filters and serialize misses so concurrent calls share a fetch.

    The Korean date belongs in the key: yesterday's cache cannot hide today's wins.
    Only successful responses, including empty ones, enter the cache.
    """

    def __init__(
        self,
        source: WinsSource,
        *,
        clock: Callable[[], float] = monotonic,
        today: Callable[[], date] = korean_today
    ):
        self.source = source
        self.clock = clock
        self.today = today
        self._cache = OrderedDict()
        self._lock = asyncio.Lock()

    async def execute(self, artist: str | None = None) -> tuple[RecordedWin, ...]:
        artist = normalize_artist(artist)
        async with self._lock:
            key = (artist, self.today())
            cached = self._cache.get(key)
            if cached is not None and cached[0] > self.clock():
                self._cache.move_to_end(key)
                return cached[1]
            wins = (await self.source.fetch(*key))[:5]
            self._cache[key] = (self.clock() + 60, wins)
            self._cache.move_to_end(key)
            while len(self._cache) > 128:
                self._cache.popitem(last=False)
            return wins
