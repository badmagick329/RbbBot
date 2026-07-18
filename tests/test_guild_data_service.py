from datetime import datetime, timedelta, timezone

import pytest
from tortoise import Tortoise

from rbb_bot.models import (
    AutoRole,
    DiscordUser,
    Greeting,
    Guild,
    GuildLogging,
    JoinEvent,
    JoinResponse,
    JoinRole,
    Reminder,
    Response,
    SourceEntry,
    Tag,
)
from rbb_bot.services.guild_data_service import GuildDataService
from tests._database import get_test_database_url


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_departure_is_recorded_once_and_survives_reinitialization(test_database):
    departed_at = datetime(2026, 7, 18, tzinfo=timezone.utc)
    guild = await Guild.create(id=1234)

    assert await GuildDataService.record_departure(guild.id, departed_at) is True
    assert (
        await GuildDataService.record_departure(
            guild.id, departed_at + timedelta(days=1)
        )
        is False
    )

    await guild.refresh_from_db()
    assert guild.departed_at == departed_at

    await Tortoise.close_connections()
    await Tortoise.init(
        db_url=get_test_database_url(),
        modules={"models": ["rbb_bot.models", "aerich.models"]},
    )

    reloaded = await Guild.get(id=guild.id)
    assert reloaded.departed_at == departed_at


@pytest.mark.asyncio
async def test_rejoin_clears_departure_without_removing_configuration(test_database):
    departed_at = datetime(2026, 7, 18, tzinfo=timezone.utc)
    guild = await Guild.create(id=1234, prefix="?")
    response = await Response.create(guild=guild, content="still configured")
    tag = await Tag.create(guild=guild, trigger="configured")
    await tag.responses.add(response)
    await GuildDataService.record_departure(guild.id, departed_at)

    assert await GuildDataService.record_rejoin(guild.id) is True

    await guild.refresh_from_db()
    assert guild.departed_at is None
    assert guild.prefix == "?"
    assert await Tag.filter(guild=guild, trigger="configured").exists()
    assert await GuildDataService.record_rejoin(guild.id) is False


@pytest.mark.asyncio
async def test_unconfigured_guild_lifecycle_events_do_not_create_a_record(
    test_database,
):
    assert await GuildDataService.record_departure(9999) is False
    assert await GuildDataService.record_rejoin(9999) is False
    assert await Guild.filter(id=9999).exists() is False


@pytest.mark.asyncio
async def test_expired_cleanup_candidates_use_the_seven_day_boundary(test_database):
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    expired = await Guild.create(id=1)
    recent = await Guild.create(id=2)
    active = await Guild.create(id=3)
    await GuildDataService.record_departure(expired.id, now - timedelta(days=7))
    await GuildDataService.record_departure(recent.id, now - timedelta(days=6))

    candidates = await GuildDataService.expired_cleanup_candidates(now)

    assert [guild.id for guild in candidates] == [expired.id]
    await active.refresh_from_db()
    assert active.departed_at is None


@pytest.mark.asyncio
async def test_delete_guild_data_removes_guild_scoped_data_only(test_database):
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    user = await DiscordUser.create(id=100, blacklist={"source": "blacklist"})
    guild = await Guild.create(id=1234)
    other_guild = await Guild.create(id=5678)
    greeting = await Greeting.create(guild=guild)
    logging = await GuildLogging.create(guild_model=guild, channel_id=123)
    join_event = await JoinEvent.create(guild=guild)
    join_response = await JoinResponse.create(event=join_event, content="welcome")
    join_role = await JoinRole.create(event=join_event, role_id=456)
    await join_event._responses.add(join_response)
    await join_event._roles.add(join_role)
    response = await Response.create(guild=guild, content="response")
    tag = await Tag.create(guild=guild, trigger="trigger")
    await tag.responses.add(response)
    guild_reminder = await Reminder.create(
        discord_user=user, guild=guild, due_time=now, text="guild reminder"
    )
    dm_reminder = await Reminder.create(
        discord_user=user, due_time=now, text="dm reminder"
    )
    auto_role = await AutoRole.create(guild_id=guild.id, role_id=789)
    source_entry = await SourceEntry.create(
        emoji_string="<:test:1>",
        guild_id=guild.id,
        channel_id=11,
        message_id=12,
        jump_url="https://discord.com/channels/1/11/12",
        user=user,
        conf_message_id=13,
        conf_jump_url="https://discord.com/channels/2/22/13",
    )

    await GuildDataService.record_departure(guild.id, now - timedelta(days=7))

    assert await GuildDataService.delete_guild_data(guild.id, now) is True
    assert await GuildDataService.delete_guild_data(guild.id, now) is False

    for model, record in [
        (Guild, guild),
        (Greeting, greeting),
        (GuildLogging, logging),
        (JoinEvent, join_event),
        (JoinResponse, join_response),
        (JoinRole, join_role),
        (Response, response),
        (Tag, tag),
        (Reminder, guild_reminder),
        (AutoRole, auto_role),
        (SourceEntry, source_entry),
    ]:
        assert await model.filter(pk=record.pk).exists() is False

    assert await Guild.filter(id=other_guild.id).exists() is True
    assert await Reminder.filter(pk=dm_reminder.pk).exists() is True
    saved_user = await DiscordUser.get(id=user.id)
    assert saved_user.blacklist == {"source": "blacklist"}


@pytest.mark.asyncio
async def test_delete_guild_data_rejects_active_and_rejoined_guilds(test_database):
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    guild = await Guild.create(id=1234)

    assert await GuildDataService.delete_guild_data(guild.id, now) is False

    await GuildDataService.record_departure(guild.id, now - timedelta(days=7))
    assert await GuildDataService.record_rejoin(guild.id) is True
    assert await GuildDataService.source_entries_for_cleanup(guild.id, now) is None
    assert await GuildDataService.delete_guild_data(guild.id, now) is False
    assert await Guild.filter(id=guild.id).exists() is True


@pytest.mark.asyncio
async def test_reconcile_departed_guilds_marks_only_absent_active_records(
    test_database,
):
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    active = await Guild.create(id=1)
    absent = await Guild.create(id=2)
    already_departed = await Guild.create(id=3)
    original_departure = now - timedelta(days=1)
    await GuildDataService.record_departure(already_departed.id, original_departure)

    assert await GuildDataService.reconcile_departed_guilds([active.id], now) == [
        absent.id
    ]
    assert await GuildDataService.reconcile_departed_guilds([active.id], now) == []

    await active.refresh_from_db()
    await absent.refresh_from_db()
    await already_departed.refresh_from_db()
    assert active.departed_at is None
    assert absent.departed_at == now
    assert already_departed.departed_at == original_departure
