from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class ReleaseListing:
    """A stored release as the lookup commands show it.

    `release_time` is None when the wiki gave only a day; `urls` holds the MV links,
    empty until the scraper has resolved any.
    """

    artist: str
    title: str
    album_title: str
    release_type: str
    release_date: date
    release_time: datetime | None
    urls: tuple[str, ...]


@dataclass(frozen=True)
class ReleaseFilter:
    """Case-insensitive partial matches, all of which must hold.

    An empty or missing field matches everything. `title_or_album` matches either the
    title or the album title; `comebacks` searches that way, `videos` by `title` only.
    """

    artist: str | None = None
    title: str | None = None
    title_or_album: str | None = None
    release_type: str | None = None


class ReleaseCatalogue(Protocol):
    async def search(
        self,
        criteria: ReleaseFilter,
        *,
        on_or_after: date | None = None,
        before: date | None = None,
        newest_first: bool,
    ) -> tuple[ReleaseListing, ...]:
        """Releases matching `criteria` whose release date lies in the window, by date."""
