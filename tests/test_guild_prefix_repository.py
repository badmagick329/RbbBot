import pytest

from rbb_bot.application.guild_prefixes.prefixes import (
    LoadGuildPrefixes,
    ManageGuildPrefix,
)
from rbb_bot.infrastructure.guild_prefixes.repository import (
    TortoiseGuildPrefixRepository,
)
from rbb_bot.models import Guild
from rbb_bot.settings.config import get_config

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_reading_the_prefix_creates_a_configured_guild(test_database):
    repo = TortoiseGuildPrefixRepository()

    assert await repo.prefix(1) == get_config().default_prefix
    assert await Guild.filter(id=1).count() == 1


async def test_prefix_round_trips_through_postgres_encrypted(test_database):
    prefixes = {}
    manage = ManageGuildPrefix(TortoiseGuildPrefixRepository(), prefixes)

    await manage.set(1, "zz?")

    assert await manage.read(1) == "zz?"
    stored = await Guild.get(id=1)
    assert stored.prefix_ciphertext
    assert "zz?" not in stored.prefix_ciphertext

    loaded = {}
    await LoadGuildPrefixes(TortoiseGuildPrefixRepository(), loaded).execute()
    assert loaded == {1: "zz?"}


async def test_setting_the_prefix_keeps_other_features_settings(test_database):
    await Guild.create(
        id=2, emojis_channel_id=7, reminders_enabled=True, max_custom_roles=4
    )

    await TortoiseGuildPrefixRepository().set_prefix(2, "?")

    stored = await Guild.get(id=2)
    assert stored.prefix == "?"
    assert stored.emojis_channel_id == 7
    assert stored.reminders_enabled
    assert stored.max_custom_roles == 4
    assert await Guild.all().count() == 1
