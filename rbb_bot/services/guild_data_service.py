"""Durable, non-destructive lifecycle state for configured Discord guilds."""

from datetime import datetime, timedelta, timezone

from tortoise import Tortoise


class GuildDataService:
    GRACE_PERIOD = timedelta(days=7)

    @staticmethod
    def _guild_model():
        """Use the model class registered by the active Tortoise configuration."""
        return Tortoise.apps["models"]["Guild"]

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
