from rbb_bot.application.guild_lifecycle.contracts import (
    GuildLifecycleRepository,
    OperationalLogger,
)


class RecordGuildDeparture:
    """Start a configured guild's grace period when the bot leaves it.

    Runs from a Discord listener, so a failure is logged instead of raised.
    """

    def __init__(self, repository: GuildLifecycleRepository, logger: OperationalLogger):
        self.repository = repository
        self.logger = logger

    async def execute(self, guild_id: int) -> None:
        try:
            if await self.repository.record_departure(guild_id):
                self.logger.info("Guild marked departed guild_id=%s", guild_id)
        except Exception:
            self.logger.exception(
                "Guild departure lifecycle handling failed guild_id=%s", guild_id
            )


class RecordGuildRejoin:
    """Cancel a departed guild's pending cleanup when the bot is invited back.

    Runs from a Discord listener, so a failure is logged instead of raised.
    """

    def __init__(self, repository: GuildLifecycleRepository, logger: OperationalLogger):
        self.repository = repository
        self.logger = logger

    async def execute(self, guild_id: int) -> None:
        try:
            if await self.repository.record_rejoin(guild_id):
                self.logger.info("Guild departure state cleared guild_id=%s", guild_id)
        except Exception:
            self.logger.exception(
                "Guild rejoin lifecycle handling failed guild_id=%s", guild_id
            )
