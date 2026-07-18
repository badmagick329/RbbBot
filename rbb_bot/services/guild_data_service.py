"""Durable, non-destructive lifecycle state for configured Discord guilds."""

from datetime import datetime, timedelta, timezone

from tortoise import Tortoise
from tortoise.transactions import in_transaction


class GuildDataService:
    GRACE_PERIOD = timedelta(days=7)

    @staticmethod
    def _model(model_name: str):
        """Use model classes registered by the active Tortoise configuration."""
        return Tortoise.apps["models"][model_name]

    @classmethod
    def _guild_model(cls):
        return cls._model("Guild")

    @staticmethod
    def _now(now: datetime | None) -> datetime:
        return now or datetime.now(timezone.utc)

    @classmethod
    async def record_departure(cls, guild_id: int, now: datetime | None = None) -> bool:
        """Mark a configured guild as departed without extending an existing grace period."""
        guild = await cls._guild_model().get_or_none(id=guild_id)
        if guild is None or guild.departed_at is not None:
            return False

        guild.departed_at = cls._now(now)
        await guild.save(update_fields=["departed_at"])
        return True

    @classmethod
    async def record_rejoin(cls, guild_id: int) -> bool:
        """Clear pending departure state for a previously configured guild."""
        guild = await cls._guild_model().get_or_none(id=guild_id)
        if guild is None or guild.departed_at is None:
            return False

        guild.departed_at = None
        await guild.save(update_fields=["departed_at"])
        return True

    @classmethod
    async def expired_cleanup_candidates(cls, now: datetime | None = None) -> list:
        """Return configured guilds past the grace period; never delete them."""
        deadline = cls._now(now) - cls.GRACE_PERIOD
        return (
            await cls._guild_model()
            .filter(departed_at__lte=deadline)
            .order_by("departed_at", "_id")
        )

    @classmethod
    async def source_entries_for_cleanup(
        cls, guild_id: int, now: datetime | None = None
    ) -> list | None:
        """Return source entries only when the guild remains eligible for cleanup."""
        deadline = cls._now(now) - cls.GRACE_PERIOD
        eligible = (
            await cls._guild_model()
            .filter(id=guild_id, departed_at__lte=deadline)
            .exists()
        )
        if not eligible:
            return None

        return await cls._model("SourceEntry").filter(guild_id=guild_id).order_by("id")

    @classmethod
    async def delete_guild_data(
        cls, guild_id: int, now: datetime | None = None
    ) -> bool:
        """Delete expired guild-scoped database data without touching global users."""
        deadline = cls._now(now) - cls.GRACE_PERIOD
        async with in_transaction() as connection:
            guild = await (
                cls._guild_model()
                .filter(id=guild_id, departed_at__lte=deadline)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if guild is None:
                return False

            await cls._model("AutoRole").filter(guild_id=guild_id).using_db(
                connection
            ).delete()
            await cls._model("SourceEntry").filter(guild_id=guild_id).using_db(
                connection
            ).delete()
            await guild.delete(using_db=connection)
        return True

    @classmethod
    async def reconcile_departed_guilds(
        cls, active_guild_ids: list[int] | set[int], now: datetime | None = None
    ) -> list[int]:
        """Mark legacy configured guilds absent from the ready bot cache as departed."""
        query = cls._guild_model().filter(departed_at__isnull=True)
        if active_guild_ids:
            query = query.exclude(id__in=list(active_guild_ids))

        guild_ids = await query.order_by("id").values_list("id", flat=True)
        if guild_ids:
            await cls._guild_model().filter(
                id__in=guild_ids, departed_at__isnull=True
            ).update(departed_at=cls._now(now))
        return guild_ids
