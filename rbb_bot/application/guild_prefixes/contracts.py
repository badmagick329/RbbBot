from enum import Enum
from typing import Protocol


class Refusal(Enum):
    TOO_LONG = "too_long"
    ALREADY_SET = "already_set"


class PrefixRefused(Exception):
    """A prefix change the feature turns down for a reason the requester can act on."""

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.value)
        self.refusal = refusal


class GuildPrefixRepository(Protocol):
    async def prefix(self, guild_id: int) -> str:
        """Return the guild's prefix, creating its configured-guild row if missing."""

    async def set_prefix(self, guild_id: int, prefix: str) -> None: ...

    async def all_prefixes(self) -> dict[int, str]:
        """Every configured guild's prefix, departed guilds included."""
