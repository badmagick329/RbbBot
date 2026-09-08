from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


DEFAULT_TEXT = "No Text"
MAX_TEXT = 1500


@dataclass(frozen=True)
class ReminderData:
    id: int
    user_id: int
    guild_id: int | None
    channel_id: int | None
    text: str
    due_time: datetime
    created_at: datetime
    channel_enabled: bool


@dataclass(frozen=True)
class CreateReminderRequest:
    user_id: int
    due_time: datetime
    guild_id: int | None = None
    channel_id: int | None = None
    text: str = DEFAULT_TEXT


class ReminderRepository(Protocol):
    async def create(self, request: CreateReminderRequest) -> ReminderData:
        ...

    async def get(self, reminder_id: int) -> ReminderData | None:
        ...

    async def list_for_user(self, user_id: int) -> list[ReminderData]:
        ...

    async def due_ids(self, now: datetime) -> list[int]:
        ...

    async def delete(self, reminder_id: int) -> bool:
        ...

    async def channel_enabled(self, guild_id: int) -> bool:
        ...

    async def set_channel_enabled(self, guild_id: int, enabled: bool) -> None:
        ...


class ReminderDelivery(Protocol):
    async def send(self, reminder: ReminderData, *, late: bool) -> None:
        ...


class CreateReminder:
    """Recheck confirmed input because time and guild settings can change during confirmation."""

    def __init__(self, repository: ReminderRepository):
        self.repository = repository

    async def execute(
        self, request: CreateReminderRequest, now: datetime
    ) -> ReminderData:
        if request.due_time.tzinfo is None or request.due_time <= now:
            raise ValueError("Please choose a future time with a timezone.")
        if len(request.text) > MAX_TEXT:
            raise ValueError(f"Reminder text must be at most {MAX_TEXT} characters.")
        if request.channel_id is not None and (
            request.guild_id is None
            or not await self.repository.channel_enabled(request.guild_id)
        ):
            raise ValueError(
                "Channel reminders are disabled. Please set a DM reminder."
            )
        return await self.repository.create(request)


class GetReminder:
    """Keep ownership checks identical for showing and cancelling reminders."""

    def __init__(self, repository: ReminderRepository):
        self.repository = repository

    async def execute(self, reminder_id: int, user_id: int) -> ReminderData | None:
        reminder = await self.repository.get(reminder_id)
        return reminder if reminder and reminder.user_id == user_id else None


class CancelReminder:
    def __init__(self, repository: ReminderRepository):
        self.repository = repository

    async def execute(self, reminder_id: int, user_id: int) -> bool:
        if await GetReminder(self.repository).execute(reminder_id, user_id) is None:
            return False
        return await self.repository.delete(reminder_id)


class DeliverReminder:
    """Re-read durable work and remove it only after delivery succeeds."""

    def __init__(self, repository: ReminderRepository, delivery: ReminderDelivery):
        self.repository = repository
        self.delivery = delivery

    async def execute(self, reminder_id: int, now: datetime) -> bool:
        reminder = await self.repository.get(reminder_id)
        if reminder is None or reminder.due_time > now:
            return False
        await self.delivery.send(
            reminder, late=(now - reminder.due_time).total_seconds() > 60
        )
        await self.repository.delete(reminder_id)
        return True
