import pytest

from rbb_bot.application.emotes.configure import ConfigureEmoteChannel
from rbb_bot.application.emotes.contracts import EmoteChannelSettings
from rbb_bot.infrastructure.emotes.repository import TortoiseEmoteChannelRepository
from rbb_bot.models import Guild

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_reading_settings_never_creates_a_configured_guild(test_database):
    repo = TortoiseEmoteChannelRepository()

    assert await repo.settings(1) == EmoteChannelSettings(None, None, True)
    assert await Guild.all() == []


async def test_emote_channel_settings_round_trip_through_postgres(test_database):
    configure = ConfigureEmoteChannel(TortoiseEmoteChannelRepository())

    await configure.assign(1, 7, delete_previous=False)
    await configure.set_message(1, "Enjoy the emotes")

    assert await configure.read(1) == EmoteChannelSettings(7, "Enjoy the emotes", False)
    stored = await Guild.get(id=1)
    assert stored.emojis_channel_message_ciphertext
    assert "Enjoy" not in stored.emojis_channel_message_ciphertext

    await configure.unassign(1)
    assert await configure.read(1) == EmoteChannelSettings(
        None, "Enjoy the emotes", False
    )
    await configure.clear_message(1)
    assert await configure.read(1) == EmoteChannelSettings(None, None, False)
    assert await Guild.all().count() == 1


async def test_writes_keep_other_features_settings_on_the_guild(test_database):
    await Guild.create(id=2, prefix="?", reminders_enabled=True, max_custom_roles=4)
    repo = TortoiseEmoteChannelRepository()

    await repo.assign(2, 7, delete_previous=True)
    await repo.set_message(2, "hi")
    await repo.unassign(2)

    stored = await Guild.get(id=2)
    assert stored.prefix == "?"
    assert stored.reminders_enabled
    assert stored.max_custom_roles == 4
    assert await repo.settings(2) == EmoteChannelSettings(None, "hi", True)
