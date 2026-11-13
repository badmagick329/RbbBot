import time
from typing import Callable, Protocol

from rbb_bot.application.guild_logging.configure import LoggingRepository
from rbb_bot.domain.guild_logging import GuildNotice

SUPPRESSION_SECONDS = 60 * 60


class LogChannelUnavailable(Exception):
    """The guild's log channel is deleted or closed to the bot; only the guild can fix that."""

    def __init__(self, channel_id: int):
        super().__init__(f"channel_id={channel_id}")
        self.channel_id = channel_id


class GuildNoticeChannel(Protocol):
    async def post(self, channel_id: int, notice: GuildNotice) -> None:
        """Raise `LogChannelUnavailable` when the channel is missing or forbidden."""


class OperationalLogger(Protocol):
    def warning(self, msg: str, *args) -> None: ...


class ReportGuildNotice:
    """Post a guild notice to the guild's log channel, at most once per problem per hour.

    Notices go to any configured log channel regardless of the event flags: they are about
    the bot's own configured work, not member activity. Repeats are suppressed so a join
    wave behind one missing permission cannot flood the channel. The suppression record is
    in-process memory, which holds because the bot runs as a single process; a restart
    only means one early repeat.

    A broken log channel must never break the action that reported the problem, so it
    becomes one operational warning carrying guild and channel IDs only.
    """

    def __init__(
        self,
        repository: LoggingRepository,
        channel: GuildNoticeChannel,
        logger: OperationalLogger,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.repository = repository
        self.channel = channel
        self.logger = logger
        self.clock = clock
        self._last_sent: dict[tuple, float] = {}

    async def execute(self, guild_id: int, notice: GuildNotice) -> None:
        settings = await self.repository.read(guild_id)
        # Check suppression only once a channel exists, so a guild that sets one
        # right after a failure still hears about the next occurrence.
        if settings.channel_id is None or not self._due((guild_id, notice.key)):
            return
        try:
            await self.channel.post(settings.channel_id, notice)
        except LogChannelUnavailable:
            self.log_channel_unavailable(guild_id, settings.channel_id)

    def log_channel_unavailable(self, guild_id: int, channel_id: int) -> None:
        if self._due((guild_id, "log-channel-unavailable", channel_id)):
            self.logger.warning(
                "Guild log channel unavailable guild_id=%s channel_id=%s",
                guild_id,
                channel_id,
            )

    def _due(self, key: tuple) -> bool:
        # Claim the slot before sending: concurrent join events would otherwise all
        # pass the check before the first post completes.
        now = self.clock()
        self._last_sent = {
            seen: at
            for seen, at in self._last_sent.items()
            if now - at < SUPPRESSION_SECONDS
        }
        if key in self._last_sent:
            return False
        self._last_sent[key] = now
        return True
