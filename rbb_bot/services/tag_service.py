"""Cached guild tag configuration and literal tag matching."""

import random
import re
from dataclasses import dataclass

from tortoise import Tortoise
from tortoise.expressions import F


@dataclass(frozen=True)
class CachedTag:
    id: int
    trigger: str
    inline: bool
    responses: tuple[str, ...]


@dataclass(frozen=True)
class GuildTagSnapshot:
    emojis_channel_id: int | None
    tags: tuple[CachedTag, ...]


class TagService:
    def __init__(self):
        self._guilds: dict[int, GuildTagSnapshot] = {}

    @staticmethod
    def _model(model_name: str):
        return Tortoise.apps["models"][model_name]

    async def load(self) -> None:
        guild_ids = await self._model("Guild").all().values_list("id", flat=True)
        for guild_id in guild_ids:
            await self.refresh_guild(guild_id)

    async def refresh_guild(self, guild_id: int) -> None:
        guild = await self._model("Guild").get_or_none(id=guild_id)
        if guild is None:
            self.remove_guild(guild_id)
            return
        tags = (
            await self._model("Tag").filter(guild=guild).prefetch_related("responses")
        )
        self._guilds[guild_id] = GuildTagSnapshot(
            emojis_channel_id=guild.emojis_channel_id,
            tags=tuple(
                CachedTag(
                    id=tag.id,
                    trigger=tag.trigger,
                    inline=tag.inline,
                    responses=tuple(response.content for response in tag.responses),
                )
                for tag in tags
                if tag.responses
            ),
        )

    def remove_guild(self, guild_id: int) -> None:
        self._guilds.pop(guild_id, None)

    def match(
        self, guild_id: int, channel_id: int, message_content: str
    ) -> CachedTag | None:
        snapshot = self._guilds.get(guild_id)
        if snapshot is None or snapshot.emojis_channel_id == channel_id:
            return None

        normalized = message_content.lower().strip()
        for tag in snapshot.tags:
            if not tag.inline and tag.trigger == normalized:
                return tag
        for tag in snapshot.tags:
            if tag.inline and re.search(
                rf"(?<!\w){re.escape(tag.trigger)}(?!\w)", normalized
            ):
                return tag
        return None

    async def choose_response(self, tag: CachedTag) -> str:
        await self._model("Tag").filter(id=tag.id).update(use_count=F("use_count") + 1)
        return random.choice(tag.responses)
