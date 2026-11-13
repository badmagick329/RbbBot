from typing import MutableMapping

from rbb_bot.application.guild_prefixes.contracts import (
    GuildPrefixRepository,
    PrefixRefused,
    Refusal,
)
from rbb_bot.domain.guild_prefixes import MAX_PREFIX_LENGTH


class ManageGuildPrefix:
    """Show or change a guild's prefix.

    `prefixes` is the bot's in-memory map that command parsing reads on every message,
    so a stored change is copied into it at once; the database is read only at startup.
    """

    def __init__(
        self, repository: GuildPrefixRepository, prefixes: MutableMapping[int, str]
    ):
        self.repository = repository
        self.prefixes = prefixes

    async def read(self, guild_id: int) -> str:
        return await self.repository.prefix(guild_id)

    async def set(self, guild_id: int, prefix: str) -> None:
        # The current prefix is read before validating, as the command always did, so
        # even a refused change leaves the guild with a configured-guild row.
        current = await self.repository.prefix(guild_id)
        if len(prefix) > MAX_PREFIX_LENGTH:
            raise PrefixRefused(Refusal.TOO_LONG)
        if current == prefix:
            raise PrefixRefused(Refusal.ALREADY_SET)
        await self.repository.set_prefix(guild_id, prefix)
        self.prefixes[guild_id] = prefix


class LoadGuildPrefixes:
    """Fill the bot's in-memory prefix map from storage before any command is parsed."""

    def __init__(
        self, repository: GuildPrefixRepository, prefixes: MutableMapping[int, str]
    ):
        self.repository = repository
        self.prefixes = prefixes

    async def execute(self) -> None:
        self.prefixes.update(await self.repository.all_prefixes())
