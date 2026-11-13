from typing import Callable

from rbb_bot.application.emotes.contracts import (
    EmoteChannelRefused,
    EmoteChannelRepository,
    EmoteChannelSettings,
    Refusal,
)
from rbb_bot.domain.emotes import MAX_CHANNEL_MESSAGE


class ConfigureEmoteChannel:
    """Choose a guild's emote channel and the message posted after its emotes.

    The tag listener ignores the emote channel and caches that choice per guild, so every
    change of channel calls `on_channel_change` with the guild ID. The caller wires it to
    whatever cache needs it; the emote feature itself keeps no cache.
    """

    def __init__(
        self,
        repository: EmoteChannelRepository,
        on_channel_change: Callable[[int], None] = lambda guild_id: None,
    ):
        self.repository = repository
        self.on_channel_change = on_channel_change

    async def read(self, guild_id: int) -> EmoteChannelSettings:
        return await self.repository.settings(guild_id)

    async def assign(
        self, guild_id: int, channel_id: int, delete_previous: bool
    ) -> None:
        # Reassigning the same channel is refused even when `delete_previous` differs.
        if (await self.repository.settings(guild_id)).channel_id == channel_id:
            raise EmoteChannelRefused(Refusal.ALREADY_ASSIGNED)
        await self.repository.assign(guild_id, channel_id, delete_previous)
        self.on_channel_change(guild_id)

    async def unassign(self, guild_id: int) -> None:
        await self.repository.unassign(guild_id)
        self.on_channel_change(guild_id)

    async def set_message(self, guild_id: int, message: str) -> None:
        if len(message) > MAX_CHANNEL_MESSAGE:
            raise EmoteChannelRefused(Refusal.MESSAGE_TOO_LONG)
        await self.repository.set_message(guild_id, message)

    async def clear_message(self, guild_id: int) -> None:
        await self.repository.set_message(guild_id, None)
