from typing import Callable

from rbb_bot.application.tags.contracts import TagCatalog, TagPreferences, TagRepository
from rbb_bot.domain.tags.rules import TagResponse, match_tag


class SelectTagResponse:
    """Keep audience policy, matching, selection, and use accounting outside Discord listeners."""

    def __init__(
        self,
        catalog: TagCatalog,
        repository: TagRepository,
        preferences: TagPreferences,
        choose: Callable[[tuple[TagResponse, ...]], TagResponse],
    ):
        self.catalog = catalog
        self.repository = repository
        self.preferences = preferences
        self.choose = choose

    def accepts_author(self, user_id: int) -> bool:
        return not self.preferences.is_opted_out(user_id)

    async def execute(
        self, guild_id: int, channel_id: int, user_id: int, content: str
    ) -> str | None:
        if not self.accepts_author(user_id):
            return None
        snapshot = await self.catalog.get(guild_id)
        if snapshot.emojis_channel_id == channel_id:
            return None
        tag = match_tag(snapshot.tags, content)
        if tag is None:
            return None
        response = self.choose(tag.responses)
        await self.repository.record_use(tag.id)
        return response.content
