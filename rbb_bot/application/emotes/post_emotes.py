from typing import Awaitable, Callable, Protocol

from rbb_bot.application.emotes.channel_notice import emote_channel_notice
from rbb_bot.application.emotes.contracts import (
    EmoteChannelRefused,
    EmoteChannelRepository,
    EmoteChannelUnavailable,
    EmotePoster,
    OperationalLogger,
    Refusal,
)
from rbb_bot.domain.guild_logging import GuildNotice


class GuildNotices(Protocol):
    async def execute(self, guild_id: int, notice: GuildNotice) -> None: ...


class PostEmotesNow:
    """Post the guild's emotes on an administrator's request.

    The requester is present, so problems come back to them: refusals as
    `EmoteChannelRefused`, an unavailable channel as `EmoteChannelUnavailable`. Permissions
    are checked only when previous posts will be deleted, because only clearing needs more
    than sending.
    """

    def __init__(self, repository: EmoteChannelRepository, poster: EmotePoster):
        self.repository = repository
        self.poster = poster

    async def execute(
        self, guild_id: int, announce: Callable[[int], Awaitable[None]]
    ) -> None:
        """`announce` receives the channel ID once checks pass, before anything is posted."""
        settings = await self.repository.settings(guild_id)
        if settings.channel_id is None:
            raise EmoteChannelRefused(Refusal.NO_CHANNEL)
        access = await self.poster.access(settings.channel_id)
        if settings.delete_previous and not access.manage_messages:
            raise EmoteChannelRefused(Refusal.MISSING_MANAGE_MESSAGES)
        if settings.delete_previous and not access.read_message_history:
            raise EmoteChannelRefused(Refusal.MISSING_READ_HISTORY)
        await announce(settings.channel_id)
        await self.poster.post(
            settings.channel_id, settings.message, settings.delete_previous
        )


class RepostEmotes:
    """Repost the guild's emotes after they changed, with nobody waiting on the result.

    Settings are read when the repost runs, not when it was scheduled, because the guild
    may change or clear its emote channel while the debounce timer waits. A channel the
    guild deleted or closed to the bot becomes a WARNING plus a guild notice, since only
    the guild can fix it; any other failure propagates to the caller as a bug.
    """

    def __init__(
        self,
        repository: EmoteChannelRepository,
        poster: EmotePoster,
        notices: GuildNotices,
        logger: OperationalLogger,
    ):
        self.repository = repository
        self.poster = poster
        self.notices = notices
        self.logger = logger

    async def execute(self, guild_id: int) -> None:
        settings = await self.repository.settings(guild_id)
        if settings.channel_id is None:
            return
        try:
            await self.poster.post(
                settings.channel_id, settings.message, settings.delete_previous
            )
        except EmoteChannelUnavailable as error:
            self.logger.warning(
                "Emoji update failed guild_id=%s channel_id=%s",
                guild_id,
                error.channel_id,
                exc_info=error,
            )
            await self.notices.execute(
                guild_id, emote_channel_notice(error.channel_id, error.deleted)
            )
