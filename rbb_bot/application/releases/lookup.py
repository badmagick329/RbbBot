from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

import pendulum

from rbb_bot.application.releases.contracts import (
    ReleaseCatalogue,
    ReleaseFilter,
    ReleaseListing,
)

# `comebacks` without a start date shows releases from this many days ago onwards,
# so a release from the last couple of days still shows up.
RECENT_DAYS = 2


class SearchTermMissing(Exception):
    """`videos` was asked to search with neither an artist nor a release name."""


class FindVideos:
    """List every stored MV link of the matching releases, newest release first."""

    def __init__(self, catalogue: ReleaseCatalogue):
        self.catalogue = catalogue

    async def execute(
        self, artist: str | None, title: str | None
    ) -> tuple[tuple[str, ReleaseListing], ...]:
        if artist is None and title is None:
            raise SearchTermMissing
        releases = await self.catalogue.search(
            ReleaseFilter(artist=artist, title=title), newest_first=True
        )
        return tuple((url, release) for release in releases for url in release.urls)


@dataclass(frozen=True)
class UpcomingReleases:
    """`showing_older` marks the fallback to releases before today, newest first."""

    releases: tuple[ReleaseListing, ...]
    showing_older: bool


class ListReleases:
    """Show releases from a start date onwards, falling back to older ones when none match.

    The fallback only applies when the requester gave no start date. A start date the
    command could not parse still counts as given: the window then starts at the default,
    but no fallback follows, as the command always behaved.
    """

    def __init__(
        self,
        catalogue: ReleaseCatalogue,
        today: Callable[[], date] = lambda: pendulum.today().date(),
    ):
        self.catalogue = catalogue
        self.today = today

    async def execute(
        self,
        criteria: ReleaseFilter,
        start: date | None = None,
        start_requested: bool = False,
    ) -> UpcomingReleases:
        if start is None:
            start = self.today() - timedelta(days=RECENT_DAYS)
        releases = await self.catalogue.search(
            criteria, on_or_after=start, newest_first=False
        )
        if releases or start_requested:
            return UpcomingReleases(releases, showing_older=False)
        older = await self.catalogue.search(
            criteria, before=self.today(), newest_first=True
        )
        return UpcomingReleases(older, showing_older=True)
