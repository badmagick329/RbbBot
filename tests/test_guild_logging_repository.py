import asyncio

import pytest
from rbb_bot.application.guild_logging.configure import (
    ConfigureLogging,
    LoggingSettings,
)
from rbb_bot.infrastructure.guild_logging.repository import TortoiseLoggingRepository
from rbb_bot.models import Guild, GuildLogging

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_logging_reads_are_nonmutating_and_configuration_survives_disable(
    test_database,
):
    use_case = ConfigureLogging(TortoiseLoggingRepository())
    assert await use_case.read(1) == LoggingSettings()
    assert await Guild.all() == []
    await use_case.set_channel(1, 12)
    await asyncio.gather(
        use_case.set_events(1, member_join=True),
        use_case.set_events(1, message_removed=True),
    )
    assert await use_case.channel_for(1, "member_join") == 12
    assert await use_case.channel_for(1, "message_edited") is None
    await use_case.set_channel(1, None)
    assert await use_case.channel_for(1, "member_join") is None
    assert (await use_case.read(1)).message_removed
    assert await GuildLogging.all().count() == 1
