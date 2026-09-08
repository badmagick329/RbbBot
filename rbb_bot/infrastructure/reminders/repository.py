from rbb_bot.application.reminders.use_cases import CreateReminderRequest, ReminderData
from rbb_bot.models import DiscordUser, Guild, Reminder


class TortoiseReminderRepository:
    """Map the existing encrypted schema to application data without a database migration."""

    @staticmethod
    def _data(row: Reminder) -> ReminderData:
        return ReminderData(
            id=row.id,
            user_id=row.discord_user.id,
            guild_id=row.guild.id if row.guild else None,
            channel_id=row.channel_id,
            text=row.text,
            due_time=row.due_time,
            created_at=row.created_at,
            channel_enabled=bool(row.guild and row.guild.reminders_enabled),
        )

    async def create(self, request: CreateReminderRequest) -> ReminderData:
        user, _ = await DiscordUser.get_or_create(id=request.user_id)
        guild = None
        if request.guild_id is not None:
            guild, _ = await Guild.get_or_create(id=request.guild_id)
        row = await Reminder.create(
            discord_user=user,
            guild=guild,
            channel_id=request.channel_id,
            text=request.text,
            due_time=request.due_time,
        )
        await row.fetch_related("discord_user", "guild")
        return self._data(row)

    async def get(self, reminder_id: int) -> ReminderData | None:
        row = (
            await Reminder.filter(id=reminder_id)
            .prefetch_related("discord_user", "guild")
            .first()
        )
        return self._data(row) if row else None

    async def list_for_user(self, user_id: int) -> list[ReminderData]:
        rows = (
            await Reminder.filter(discord_user__id=user_id)
            .prefetch_related("discord_user", "guild")
            .order_by("due_time", "id")
        )
        return [self._data(row) for row in rows]

    async def due_ids(self, now) -> list[int]:
        return (
            await Reminder.filter(due_time__lte=now)
            .order_by("due_time", "id")
            .values_list("id", flat=True)
        )

    async def delete(self, reminder_id: int) -> bool:
        return bool(await Reminder.filter(id=reminder_id).delete())

    async def channel_enabled(self, guild_id: int) -> bool:
        guild = await Guild.get_or_none(id=guild_id)
        return bool(guild and guild.reminders_enabled)

    async def set_channel_enabled(self, guild_id: int, enabled: bool) -> None:
        await Guild.update_or_create(
            id=guild_id, defaults={"reminders_enabled": enabled}
        )
