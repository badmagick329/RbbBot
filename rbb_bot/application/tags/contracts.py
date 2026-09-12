from dataclasses import dataclass
from typing import Protocol

from rbb_bot.domain.tags.rules import GuildTags, TagDefinition, TagResponse


@dataclass(frozen=True)
class TagSelector:
    guild_id: int
    tag_id: int | None = None
    trigger: str | None = None


@dataclass(frozen=True)
class AddTagResult:
    tag: TagDefinition
    status: str


class TagRepository(Protocol):
    async def guild_ids(self) -> list[int]:
        ...

    async def snapshot(self, guild_id: int) -> GuildTags:
        ...

    async def find_tag(self, selector: TagSelector) -> TagDefinition | None:
        ...

    async def responses(self, guild_id: int) -> list[TagResponse]:
        ...

    async def add(
        self, guild_id: int, trigger: str, response: str, inline: bool
    ) -> AddTagResult:
        ...

    async def rename(
        self, guild_id: int, tag_id: int, trigger: str
    ) -> TagDefinition | None:
        ...

    async def remove_tag(self, guild_id: int, tag_id: int) -> bool:
        ...

    async def remove_responses(
        self, guild_id: int, response_ids: tuple[int, ...]
    ) -> int:
        ...

    async def record_use(self, tag_id: int) -> None:
        ...


class TagCatalog(Protocol):
    async def get(self, guild_id: int) -> GuildTags:
        ...

    def invalidate(self, guild_id: int) -> None:
        ...


class TagPreferences(Protocol):
    def is_opted_out(self, user_id: int) -> bool:
        ...
