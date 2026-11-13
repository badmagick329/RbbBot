from dataclasses import dataclass
from enum import Enum
from typing import Protocol


@dataclass(frozen=True)
class EmoteChannelSettings:
    """A guild's emote-channel settings; the defaults match a guild with no stored row."""

    channel_id: int | None = None
    message: str | None = None
    delete_previous: bool = True


@dataclass(frozen=True)
class ChannelAccess:
    """The bot's permissions in the emote channel that clearing previous posts needs."""

    manage_messages: bool
    read_message_history: bool


class Refusal(Enum):
    ALREADY_ASSIGNED = "already_assigned"
    MESSAGE_TOO_LONG = "message_too_long"
    NO_CHANNEL = "no_channel"
    MISSING_MANAGE_MESSAGES = "missing_manage_messages"
    MISSING_READ_HISTORY = "missing_read_history"


class EmoteChannelRefused(Exception):
    """A request the feature turns down for a reason the requester can act on."""

    def __init__(self, refusal: Refusal):
        super().__init__(refusal.value)
        self.refusal = refusal


class EmoteChannelUnavailable(Exception):
    """The emote channel is deleted or closed to the bot; only the guild can fix that.

    The Discord adapter raises this in place of Discord's own error, chained to it, so the
    use cases can tell a guild-caused failure from a bug without depending on discord.py.
    """

    def __init__(self, channel_id: int, deleted: bool):
        super().__init__(f"channel_id={channel_id} deleted={deleted}")
        self.channel_id = channel_id
        self.deleted = deleted


class EmoteChannelRepository(Protocol):
    async def settings(self, guild_id: int) -> EmoteChannelSettings: ...

    async def assign(
        self, guild_id: int, channel_id: int, delete_previous: bool
    ) -> None: ...

    async def unassign(self, guild_id: int) -> None: ...

    async def set_message(self, guild_id: int, message: str | None) -> None: ...


class EmotePoster(Protocol):
    """One Discord guild's emotes and the channels they can be posted to."""

    async def access(self, channel_id: int) -> ChannelAccess: ...

    async def post(
        self, channel_id: int, message: str | None, delete_previous: bool
    ) -> None:
        """Raise `EmoteChannelUnavailable` when the channel is missing or forbidden."""


class OperationalLogger(Protocol):
    def warning(self, msg: str, *args, **kwargs) -> None: ...
