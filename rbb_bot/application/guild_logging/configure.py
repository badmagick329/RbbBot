from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LoggingSettings:
    channel_id: int | None = None
    member_join: bool = False
    member_leave: bool = False
    message_removed: bool = False
    message_edited: bool = False


class LoggingRepository(Protocol):
    async def read(self, guild_id: int) -> LoggingSettings:
        ...

    async def update(self, guild_id: int, changes: dict) -> LoggingSettings:
        ...


class ConfigureLogging:
    """Keep channel selection and individual event flags independent, including while disabled."""

    def __init__(self, repository: LoggingRepository):
        self.repository = repository

    async def read(self, guild_id):
        return await self.repository.read(guild_id)

    async def set_channel(self, guild_id, channel_id):
        return await self.repository.update(guild_id, {"channel_id": channel_id})

    async def set_events(self, guild_id, **events):
        changes = {
            key + "_enabled": value
            for key, value in events.items()
            if value is not None
        }
        if not changes:
            raise ValueError("Specify at least one logging option to enable or disable")
        return await self.repository.update(guild_id, changes)

    async def channel_for(self, guild_id, event):
        settings = await self.repository.read(guild_id)
        return settings.channel_id if getattr(settings, event) else None
