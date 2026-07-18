import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest


sys.path.insert(0, str(Path(__file__).parents[1] / "rbb_bot"))
from rbb_bot.cogs.guild_cog import GuildCog


@pytest.mark.asyncio
async def test_guild_lifecycle_listeners_delegate_with_guild_id():
    bot = SimpleNamespace(logger=Mock())
    cog = GuildCog(bot)
    guild = SimpleNamespace(id=1234)

    with patch(
        "rbb_bot.cogs.guild_cog.GuildDataService.record_departure",
        new=AsyncMock(return_value=True),
    ) as record_departure:
        await cog.on_guild_remove(guild)

    with patch(
        "rbb_bot.cogs.guild_cog.GuildDataService.record_rejoin",
        new=AsyncMock(return_value=True),
    ) as record_rejoin:
        await cog.on_guild_join(guild)

    record_departure.assert_awaited_once_with(1234)
    record_rejoin.assert_awaited_once_with(1234)
    assert bot.logger.info.call_count == 2


@pytest.mark.asyncio
async def test_cleanup_candidate_report_logs_ids_without_deleting_data():
    bot = SimpleNamespace(logger=Mock())
    cog = GuildCog(bot)
    candidates = [SimpleNamespace(id=2), SimpleNamespace(id=1)]

    with patch(
        "rbb_bot.cogs.guild_cog.GuildDataService.expired_cleanup_candidates",
        new=AsyncMock(return_value=candidates),
    ):
        await cog.report_expired_cleanup_candidates()

    bot.logger.warning.assert_called_once_with(
        "Guild cleanup candidates count=%s guild_ids=%s", 2, "2,1"
    )
