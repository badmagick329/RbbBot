from rbb_bot.application.tags.contracts import TagRepository
from rbb_bot.domain.tags.rules import GuildTags


class CachedTagCatalog:
    """A generation check prevents an in-flight read from restoring invalidated configuration."""

    def __init__(self, repository: TagRepository):
        self.repository = repository
        self._guilds: dict[int, GuildTags] = {}
        self._generations: dict[int, int] = {}

    async def load(self) -> None:
        for guild_id in await self.repository.guild_ids():
            await self.get(guild_id)

    async def get(self, guild_id: int) -> GuildTags:
        while guild_id not in self._guilds:
            generation = self._generations.get(guild_id, 0)
            snapshot = await self.repository.snapshot(guild_id)
            if generation == self._generations.get(guild_id, 0):
                self._guilds[guild_id] = snapshot
        return self._guilds[guild_id]

    def invalidate(self, guild_id: int) -> None:
        self._generations[guild_id] = self._generations.get(guild_id, 0) + 1
        self._guilds.pop(guild_id, None)
