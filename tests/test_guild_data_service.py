from datetime import datetime, timedelta, timezone

import pytest
from tortoise import Tortoise

from rbb_bot.models import Guild, Response, Tag
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
