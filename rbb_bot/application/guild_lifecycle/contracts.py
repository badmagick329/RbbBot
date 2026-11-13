from typing import Protocol


class GuildLifecycleRepository(Protocol):
    """Departure state and cleanup for configured guilds.

    Every cleanup step re-checks the grace period itself, so a guild that rejoins while
    cleanup runs is skipped rather than deleted.
    """

    async def record_departure(self, guild_id: int) -> bool:
        """False when the guild is unconfigured or already departed."""

    async def record_rejoin(self, guild_id: int) -> bool:
        """False when the guild is unconfigured or not departed."""

    async def expired_cleanup_candidates(self) -> list[int]:
        """IDs of departed guilds past the grace period, oldest departure first."""

    async def source_entries_for_cleanup(self, guild_id: int) -> list | None:
        """The guild's source submissions, or None once it is no longer eligible.

        The entries are opaque here; only `ConfirmationPosts.delete` reads them.
        """

    async def delete_guild_data(self, guild_id: int) -> bool:
        """False when the guild stopped being eligible before deletion."""


class ConfirmationPosts(Protocol):
    async def delete(self, guild_id: int, source_entries: list) -> bool:
        """Delete the submissions' confirmation posts; False when any could not be."""


class OperationalLogger(Protocol):
    def info(self, msg: str, *args, **kwargs) -> None: ...

    def warning(self, msg: str, *args, **kwargs) -> None: ...

    def exception(self, msg: str, *args, **kwargs) -> None: ...
