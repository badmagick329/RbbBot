from typing import Callable

from rbb_bot.application.guild_lifecycle.contracts import (
    ConfirmationPosts,
    GuildLifecycleRepository,
    OperationalLogger,
)


class CleanupExpiredGuilds:
    """Delete every departed guild's data once its grace period has ended.

    Confirmation posts go first: once the database rows are gone nothing records where
    the posts are, so a guild whose posts cannot all be deleted keeps its data until a
    later run. One guild's failure never stops the others.

    `on_guild_deleted` runs after a guild's rows are gone, for the caller's in-memory
    caches (prefix map, tag catalogue); this feature keeps none itself.
    """

    def __init__(
        self,
        repository: GuildLifecycleRepository,
        confirmation_posts: ConfirmationPosts,
        logger: OperationalLogger,
        on_guild_deleted: Callable[[int], None] = lambda guild_id: None,
    ):
        self.repository = repository
        self.confirmation_posts = confirmation_posts
        self.logger = logger
        self.on_guild_deleted = on_guild_deleted

    async def execute(self) -> list[int]:
        deleted_guild_ids = []
        for guild_id in await self.repository.expired_cleanup_candidates():
            try:
                if await self._cleanup(guild_id):
                    deleted_guild_ids.append(guild_id)
            except Exception:
                self.logger.exception("Guild cleanup failed guild_id=%s", guild_id)

        if deleted_guild_ids:
            self.logger.info(
                "Guild cleanup complete count=%s guild_ids=%s",
                len(deleted_guild_ids),
                ",".join(str(guild_id) for guild_id in deleted_guild_ids),
            )
        return deleted_guild_ids

    async def _cleanup(self, guild_id: int) -> bool:
        source_entries = await self.repository.source_entries_for_cleanup(guild_id)
        if source_entries is None:
            return False
        if not await self.confirmation_posts.delete(guild_id, source_entries):
            return False
        if not await self.repository.delete_guild_data(guild_id):
            self.logger.warning(
                "Guild cleanup skipped after source confirmation cleanup "
                "guild_id=%s",
                guild_id,
            )
            return False
        self.on_guild_deleted(guild_id)
        return True
