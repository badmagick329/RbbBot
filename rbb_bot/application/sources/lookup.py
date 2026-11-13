from dataclasses import dataclass
from datetime import date
from typing import Callable

from rbb_bot.application.sources.contracts import SourceRepository


@dataclass(frozen=True)
class SourceLookup:
    source_url: str | None
    event: str | None
    source_date: date | None
    submitter_names: tuple[str | None, ...]


class FindSource:
    """Merge every submission for an emote into one answer.

    Edits are separate submissions, so each field takes its value from the newest
    submission that set it; every distinct submitter is credited, earliest first.
    """

    def __init__(self, repository: SourceRepository):
        self.repository = repository

    async def execute(self, emote: str) -> SourceLookup | None:
        sources = await self.repository.sources(emote)
        if not sources:
            return None
        source_url = event = source_date = None
        names = {}
        for source in sources:
            source_url = source.details.source_url or source_url
            event = source.details.event or event
            source_date = source.details.source_date or source_date
            names.setdefault(source.submitter_id, source.submitter_name)
        return SourceLookup(source_url, event, source_date, tuple(names.values()))


class CountSubmissions:
    """Rank submitters by how many submissions they made.

    Counts are keyed by display name, preferring the name Discord currently shows over the
    cached one, so two submitters showing the same name share a row.
    """

    def __init__(
        self,
        repository: SourceRepository,
        current_name: Callable[[int], str | None],
    ):
        self.repository = repository
        self.current_name = current_name

    async def execute(self) -> tuple[tuple[str | None, int], ...]:
        counts = {}
        for tally in await self.repository.tallies():
            name = self.current_name(tally.submitter_id)
            if name is None:
                name = tally.cached_username
            counts[name] = counts.get(name, 0) + tally.submissions
        return tuple(sorted(counts.items(), key=lambda item: item[1], reverse=True))
