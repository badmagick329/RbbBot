from datetime import datetime, timezone

import pytest
from tortoise import Tortoise

from rbb_bot.models import DiscordUser, Reminder, SourceEntry
from rbb_bot.services.user_data_service import UserDataService
from tests._database import get_test_database_url


pytestmark = pytest.mark.integration


async def create_source_entry(user, *, message_id: int = 12):
    return await SourceEntry.create(
        emoji_string="<:test:1>",
        emoji_url="https://cdn.discordapp.com/emojis/1.webp",
        source_url="https://example.com/source",
        event="event",
        guild_id=1,
        channel_id=11,
        message_id=message_id,
        jump_url=f"https://discord.com/channels/1/11/{message_id}",
        user=user,
        conf_message_id=13,
        conf_jump_url="https://discord.com/channels/2/22/13",
    )


@pytest.mark.asyncio
async def test_export_returns_all_declared_user_data(test_database):
    user = await DiscordUser.create(
        id=1,
        cached_username="test-user",
        blacklist={"source": "blacklist"},
        tag_opt_out=True,
    )
    await Reminder.create(
        discord_user=user,
        due_time=datetime(2026, 7, 18, tzinfo=timezone.utc),
        text="private reminder",
    )
    await create_source_entry(user)

    assert await UserDataService.export(999) == {
        "discord_user": None,
        "reminders": [],
        "source_entries": [],
    }

    exported = await UserDataService.export(user.id)
    assert exported["discord_user"] == {
        "id": 1,
        "cached_username": "test-user",
        "blacklist": {"source": "blacklist"},
        "tag_opt_out": True,
    }
    assert exported["reminders"][0]["text"] == "private reminder"
    assert exported["source_entries"][0]["jump_url"].endswith("/12")
    assert exported["source_entries"][0]["source_url"] == "https://example.com/source"


@pytest.mark.asyncio
async def test_delete_user_data_removes_only_requested_users_records(test_database):
    user = await DiscordUser.create(
        id=1,
        cached_username="delete-me",
        blacklist={"source": "blacklist"},
        tag_opt_out=True,
    )
    other_user = await DiscordUser.create(id=2, cached_username="keep-me")
    reminder = await Reminder.create(
        discord_user=user,
        due_time=datetime(2026, 7, 18, tzinfo=timezone.utc),
        text="delete me",
    )
    source = await create_source_entry(user)
    other_reminder = await Reminder.create(
        discord_user=other_user,
        due_time=datetime(2026, 7, 18, tzinfo=timezone.utc),
        text="keep me",
    )
    other_source = await create_source_entry(other_user, message_id=99)
    await UserDataService.load_tag_opt_out_cache()

    assert UserDataService.is_tag_opted_out(user.id) is True
    assert await UserDataService.delete_user_data(user.id) is True
    assert await UserDataService.delete_user_data(user.id) is False

    assert await DiscordUser.filter(id=user.id).exists() is False
    assert await Reminder.filter(pk=reminder.pk).exists() is False
    assert await SourceEntry.filter(pk=source.pk).exists() is False
    assert UserDataService.is_tag_opted_out(user.id) is False
    assert await DiscordUser.filter(id=other_user.id).exists() is True
    assert await Reminder.filter(pk=other_reminder.pk).exists() is True
    assert await SourceEntry.filter(pk=other_source.pk).exists() is True


@pytest.mark.asyncio
async def test_tag_opt_out_cache_persists_across_reinitialization(test_database):
    await UserDataService.set_tag_opt_out(1, True)
    assert UserDataService.is_tag_opted_out(1) is True

    await Tortoise.close_connections()
    await Tortoise.init(
        db_url=get_test_database_url(),
        modules={"models": ["rbb_bot.models", "aerich.models"]},
    )
    UserDataService._tag_opt_out_ids = set()
    await UserDataService.load_tag_opt_out_cache()

    assert UserDataService.is_tag_opted_out(1) is True
    assert await UserDataService.set_tag_opt_out(1, False) is True
    assert UserDataService.is_tag_opted_out(1) is False
