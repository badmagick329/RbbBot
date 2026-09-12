from typing import Protocol


class ReleaseSource(Protocol):
    async def read(self, url: str, saved: list[dict]) -> list[dict]:
        ...


class ReleaseStore(Protocol):
    async def read(self) -> list[dict]:
        ...

    async def save(self, releases: list[dict]) -> None:
        ...


class RefreshReleases:
    """Combine every source before committing, so partial source or database failures cannot truncate a refresh."""

    def __init__(self, source: ReleaseSource, repository: ReleaseStore):
        self.source = source
        self.repository = repository

    async def execute(self, urls):
        saved = await self.repository.read()
        for url in urls:
            incoming = await self.source.read(url, saved)
            replaced_dates = {release["release_date"] for release in incoming}
            saved = [
                release
                for release in saved
                if release["release_date"] not in replaced_dates
            ] + incoming
        await self.repository.save(saved)
