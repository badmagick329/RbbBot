import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from rbb_bot.application.reminders.use_cases import (
    ReminderData,
    CreateReminderRequest,
    CreateReminder,
    CancelReminder,
    GetReminder,
    DeliverReminder,
)
from rbb_bot.infrastructure.reminders.discord_delivery import DiscordReminderDelivery
from rbb_bot.infrastructure.reminders.worker import ReminderWorker

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def reminder(**changes):
    return replace(ReminderData(1, 42, 10, 20, "hello", NOW, NOW, True), **changes)


class MemoryRepository:
    def __init__(self, *rows):
        self.rows = {row.id: row for row in rows}
        self.enabled = True

    async def get(self, id):
        return self.rows.get(id)

    async def delete(self, id):
        return self.rows.pop(id, None) is not None

    async def due_ids(self, now):
        return [row.id for row in self.rows.values() if row.due_time <= now]

    async def channel_enabled(self, guild_id):
        return self.enabled

    async def create(self, request):
        row = reminder(
            user_id=request.user_id,
            due_time=request.due_time,
            text=request.text,
            guild_id=request.guild_id,
            channel_id=request.channel_id,
        )
        self.rows[row.id] = row
        return row


async def test_cancelled_or_privacy_deleted_reminder_is_not_delivered():
    repo = MemoryRepository(reminder())
    delivery = SimpleNamespace(send=AsyncMock())
    assert await CancelReminder(repo).execute(1, 42)
    assert not await DeliverReminder(repo, delivery).execute(1, NOW)
    delivery.send.assert_not_awaited()


async def test_ownership_is_required_to_read_and_cancel():
    repo = MemoryRepository(reminder())
    assert await GetReminder(repo).execute(1, 99) is None
    assert not await CancelReminder(repo).execute(1, 99)
    assert await repo.get(1) is not None


async def test_delivery_failure_retains_reminder_for_successful_retry():
    repo = MemoryRepository(reminder())
    delivery = SimpleNamespace(
        send=AsyncMock(side_effect=[RuntimeError("offline"), None])
    )
    use_case = DeliverReminder(repo, delivery)
    with pytest.raises(RuntimeError):
        await use_case.execute(1, NOW)
    assert await repo.get(1) is not None
    assert await use_case.execute(1, NOW)
    assert await repo.get(1) is None


async def test_worker_recovers_overdue_rows_and_isolates_failure():
    repo = MemoryRepository(
        reminder(),
        reminder(id=2),
        reminder(id=3, due_time=datetime(2100, 1, 1, tzinfo=timezone.utc)),
    )
    delivery = SimpleNamespace(
        send=AsyncMock(side_effect=[RuntimeError("offline"), None])
    )
    bot = SimpleNamespace(logger=Mock())
    worker = ReminderWorker(repo, DeliverReminder(repo, delivery), bot)
    await worker.run_once()
    assert set(repo.rows) == {1, 3}
    assert delivery.send.await_count == 2
    assert delivery.send.await_args.kwargs["late"]


async def test_unload_cancels_worker_waiting_for_discord():
    waiting = asyncio.Event()
    bot = SimpleNamespace(wait_until_ready=waiting.wait, logger=Mock())
    repo = SimpleNamespace(due_ids=AsyncMock())
    worker = ReminderWorker(repo, Mock(), bot)
    worker.start()
    await asyncio.sleep(0)
    await worker.close()
    waiting.set()
    assert worker.task.cancelled()
    repo.due_ids.assert_not_awaited()


@pytest.mark.parametrize(
    "changes",
    [
        {"due_time": NOW},
        {"due_time": NOW.replace(tzinfo=None)},
        {"text": "x" * 1501},
        {"channel_id": 20, "guild_id": None},
    ],
)
async def test_create_rejects_invalid_confirmed_input(changes):
    repo = MemoryRepository()
    request = replace(CreateReminderRequest(42, NOW + timedelta(hours=1)), **changes)
    with pytest.raises(ValueError):
        await CreateReminder(repo).execute(request, NOW)
    assert not repo.rows


async def test_create_rechecks_guild_setting_and_preserves_text():
    repo = MemoryRepository()
    request = CreateReminderRequest(
        42, NOW + timedelta(hours=1), 10, 20, "private text"
    )
    repo.enabled = False
    with pytest.raises(ValueError):
        await CreateReminder(repo).execute(request, NOW)
    repo.enabled = True
    row = await CreateReminder(repo).execute(request, NOW)
    assert row.text == "private text"


@pytest.mark.parametrize("error_type", [discord.Forbidden, discord.NotFound])
async def test_channel_send_failure_falls_back_to_uncached_user(error_type):
    error = error_type(SimpleNamespace(status=403, reason="unavailable"), "unavailable")
    channel = SimpleNamespace(send=AsyncMock(side_effect=error))
    user = SimpleNamespace(send=AsyncMock())
    bot = SimpleNamespace(
        get_channel=Mock(return_value=channel),
        get_user=Mock(return_value=None),
        fetch_user=AsyncMock(return_value=user),
    )
    await DiscordReminderDelivery(bot).send(reminder(), late=False)
    bot.fetch_user.assert_awaited_once_with(42)
    assert "hello" in user.send.await_args.args[0]


async def test_disabled_channel_goes_directly_to_dm():
    user = SimpleNamespace(send=AsyncMock())
    bot = SimpleNamespace(get_channel=Mock(), get_user=Mock(return_value=user))
    await DiscordReminderDelivery(bot).send(reminder(channel_enabled=False), late=False)
    bot.get_channel.assert_not_called()
    assert "disabled" in user.send.await_args.args[0]


async def test_uncached_channel_is_fetched_and_sent_without_dm():
    channel = SimpleNamespace(send=AsyncMock())
    bot = SimpleNamespace(
        get_channel=Mock(return_value=None),
        fetch_channel=AsyncMock(return_value=channel),
        get_user=Mock(),
    )
    await DiscordReminderDelivery(bot).send(reminder(), late=False)
    bot.fetch_channel.assert_awaited_once_with(20)
    channel.send.assert_awaited_once()
    bot.get_user.assert_not_called()


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2027-01-15 17:00", datetime(2027, 1, 15, 17, tzinfo=timezone.utc)),
        ("2027-01-15 17:00 +0900", datetime(2027, 1, 15, 8, tzinfo=timezone.utc)),
        ("in 2 minutes", NOW + timedelta(minutes=2)),
    ],
)
async def test_time_parser_uses_utc_and_respects_explicit_offsets(value, expected):
    from rbb_bot.infrastructure.reminders.time_parser import parse_reminder_time

    assert parse_reminder_time(value, NOW) == expected


async def test_worker_unload_waits_for_in_flight_delivery_cancellation():
    started = asyncio.Event()
    finished = asyncio.Event()

    async def send(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    repo = MemoryRepository(reminder())
    bot = SimpleNamespace(wait_until_ready=AsyncMock(), logger=Mock())
    worker = ReminderWorker(
        repo, DeliverReminder(repo, SimpleNamespace(send=send)), bot
    )
    worker.start()
    await started.wait()
    await worker.close()
    assert finished.is_set()
    assert await repo.get(1) is not None
