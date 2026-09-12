from dataclasses import dataclass

from rbb_bot.application.tags.contracts import (
    AddTagResult,
    TagCatalog,
    TagRepository,
    TagSelector,
)
from rbb_bot.domain.tags.rules import (
    TagDefinition,
    TagResponse,
    TagInputError,
    normalize_trigger,
    normalize_response,
)


@dataclass(frozen=True)
class AddTagRequest:
    guild_id: int
    trigger: str
    response: str
    inline: bool = False


@dataclass(frozen=True)
class RenameTagRequest:
    guild_id: int
    tag_id: int
    trigger: str


class AddTag:
    def __init__(self, repository: TagRepository, catalog: TagCatalog):
        self.repository = repository
        self.catalog = catalog

    async def execute(self, request: AddTagRequest) -> AddTagResult:
        result = await self.repository.add(
            request.guild_id,
            normalize_trigger(request.trigger),
            normalize_response(request.response),
            request.inline,
        )
        self.catalog.invalidate(request.guild_id)
        return result


class FindTag:
    def __init__(self, repository: TagRepository):
        self.repository = repository

    async def execute(self, selector: TagSelector) -> TagDefinition | None:
        if selector.tag_id is None and selector.trigger is None:
            raise TagInputError("Either trigger or tag_id is required")
        trigger = (
            normalize_trigger(selector.trigger)
            if selector.trigger is not None and selector.tag_id is None
            else None
        )
        return await self.repository.find_tag(
            TagSelector(selector.guild_id, selector.tag_id, trigger)
        )


class ListTags:
    def __init__(self, repository: TagRepository):
        self.repository = repository

    async def execute(self, guild_id: int) -> tuple[TagDefinition, ...]:
        return (await self.repository.snapshot(guild_id)).tags


class RenameTag:
    """Recheck existence and uniqueness after the user confirms the selected tag ID."""

    def __init__(self, repository: TagRepository, catalog: TagCatalog):
        self.repository = repository
        self.catalog = catalog

    async def execute(self, request: RenameTagRequest) -> TagDefinition | None:
        result = await self.repository.rename(
            request.guild_id, request.tag_id, normalize_trigger(request.trigger)
        )
        self.catalog.invalidate(request.guild_id)
        return result


class RemoveTag:
    def __init__(self, repository: TagRepository, catalog: TagCatalog):
        self.repository = repository
        self.catalog = catalog

    async def execute(self, guild_id: int, tag_id: int) -> bool:
        removed = await self.repository.remove_tag(guild_id, tag_id)
        self.catalog.invalidate(guild_id)
        return removed


class FindResponses:
    def __init__(self, repository: TagRepository):
        self.repository = repository

    async def execute(
        self, guild_id: int, response_id: int | None, content: str | None
    ) -> list[TagResponse]:
        if response_id is None and content is None:
            raise TagInputError("Either response or response_id is required")
        responses = await self.repository.responses(guild_id)
        if response_id is not None:
            return [response for response in responses if response.id == response_id]
        return [response for response in responses if response.content == content]


class FindGfycatResponses:
    def __init__(self, repository: TagRepository):
        self.repository = repository

    async def execute(self, guild_id: int) -> list[TagResponse]:
        return [
            response
            for response in await self.repository.responses(guild_id)
            if "https://gfycat.com" in response.content
            or "https://www.gfycat.com" in response.content
        ]


class RemoveResponses:
    """Delete only the response IDs shown in the confirmation, not later additions."""

    def __init__(self, repository: TagRepository, catalog: TagCatalog):
        self.repository = repository
        self.catalog = catalog

    async def execute(self, guild_id: int, response_ids: tuple[int, ...]) -> int:
        count = await self.repository.remove_responses(guild_id, response_ids)
        self.catalog.invalidate(guild_id)
        return count
