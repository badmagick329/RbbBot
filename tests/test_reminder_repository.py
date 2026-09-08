from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rbb_bot.application.reminders.use_cases import (
    CreateReminder,
    CreateReminderRequest,
    DeliverReminder,
)
from rbb_bot.infrastructure.reminders.repository import TortoiseReminderRepository
from rbb_bot.models import DiscordUser, Guild, Reminder

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_existing_encrypted_reminder_can_be_loaded_and_delivered(test_database):
    now = datetime.now(timezone.utc)
    user = await DiscordUser.create(id=123456)
    guild = await Guild.create(id=987654, reminders_enabled=True)
    row = await Reminder.create(
        discord_user=user,
        guild=guild,
        channel_id=5678,
        text="existing encrypted reminder",
        due_time=now,
    )
    ciphertext = row.text_ciphertext
    repo = TortoiseReminderRepository()
    loaded = await repo.get(row.id)
    assert loaded.user_id == user.id
    assert loaded.guild_id == guild.id
    assert loaded.text == "existing encrypted reminder"
    assert loaded.channel_enabled
    assert (await Reminder.get(id=row.id)).text_ciphertext == ciphertext
    assert await repo.due_ids(now) == [row.id]
    delivery = SimpleNamespace(send=AsyncMock())
    assert await DeliverReminder(repo, delivery).execute(row.id, now)
    assert not await Reminder.filter(id=row.id).exists()


async def test_create_and_list_dm_reminders_keep_existing_storage_contract(
    test_database,
):
    now = datetime.now(timezone.utc)
    repo = TortoiseReminderRepository()
    row = await CreateReminder(repo).execute(
        CreateReminderRequest(
            123456, now + timedelta(hours=1), text="new private reminder"
        ),
        now,
    )
    stored = await Reminder.get(id=row.id)
    assert stored.text_ciphertext != row.text
    assert stored.text == row.text
    assert row.guild_id is None
    assert not row.channel_enabled
    assert await repo.list_for_user(123456) == [row]
    assert await repo.list_for_user(999) == []
