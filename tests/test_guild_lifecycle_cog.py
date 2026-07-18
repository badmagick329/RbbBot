import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest


sys.path.insert(0, str(Path(__file__).parents[1] / "rbb_bot"))
from rbb_bot.cogs.guild_cog import GuildCog
from rbb_bot.cogs.admin_cog import AdminCog


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
async def test_source_confirmation_messages_are_deleted_before_database_cleanup():
    message = SimpleNamespace(delete=AsyncMock())
    channel = SimpleNamespace(fetch_message=AsyncMock(return_value=message))
    bot = SimpleNamespace(
        logger=Mock(), get_channel=Mock(return_value=channel), fetch_channel=AsyncMock()
    )
    cog = GuildCog(bot)
    source_entry = SimpleNamespace(conf_channel_id=123, conf_message_id=456)

    assert await cog.delete_source_confirmation_messages(1, [source_entry]) is True

    channel.fetch_message.assert_awaited_once_with(456)
    message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_source_confirmation_message_is_already_cleaned_up():
    not_found = discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"), "missing"
    )
    channel = SimpleNamespace(fetch_message=AsyncMock(side_effect=not_found))
    bot = SimpleNamespace(
        logger=Mock(), get_channel=Mock(return_value=channel), fetch_channel=AsyncMock()
    )
    cog = GuildCog(bot)
    source_entry = SimpleNamespace(conf_channel_id=123, conf_message_id=456)

    assert await cog.delete_source_confirmation_messages(1, [source_entry]) is True


@pytest.mark.asyncio
async def test_source_confirmation_permission_failure_blocks_cleanup():
    forbidden = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "missing access"
    )
    channel = SimpleNamespace(fetch_message=AsyncMock(side_effect=forbidden))
    bot = SimpleNamespace(
        logger=Mock(), get_channel=Mock(return_value=channel), fetch_channel=AsyncMock()
    )
    cog = GuildCog(bot)
    source_entry = SimpleNamespace(conf_channel_id=123, conf_message_id=456)

    assert await cog.delete_source_confirmation_messages(1, [source_entry]) is False

    bot.logger.exception.assert_called_once_with(
        "Guild source confirmation cleanup failed guild_id=%s " "source_entry_count=%s",
        1,
        1,
    )


@pytest.mark.asyncio
async def test_cleanup_continues_after_a_source_confirmation_failure():
    bot = SimpleNamespace(logger=Mock(), guild_prefixes={1: "?", 2: "!"})
    cog = GuildCog(bot)
    candidates = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    with patch(
        "rbb_bot.cogs.guild_cog.GuildDataService.expired_cleanup_candidates",
        new=AsyncMock(return_value=candidates),
    ), patch(
        "rbb_bot.cogs.guild_cog.GuildDataService.source_entries_for_cleanup",
        new=AsyncMock(side_effect=[[SimpleNamespace()], []]),
    ), patch.object(
        cog,
        "delete_source_confirmation_messages",
        new=AsyncMock(side_effect=[False, True]),
    ), patch(
        "rbb_bot.cogs.guild_cog.GuildDataService.delete_guild_data",
        new=AsyncMock(return_value=True),
    ) as delete_guild_data:
        await cog.cleanup_expired_guilds()

    delete_guild_data.assert_awaited_once_with(2)
    assert 1 in bot.guild_prefixes
    assert 2 not in bot.guild_prefixes
    bot.logger.info.assert_called_once_with(
        "Guild cleanup complete count=%s guild_ids=%s", 1, "2"
    )


@pytest.mark.asyncio
async def test_reconcile_guilds_command_uses_ready_guild_ids():
    ctx = SimpleNamespace(send=AsyncMock())
    bot = SimpleNamespace(
        guilds=[SimpleNamespace(id=1), SimpleNamespace(id=2)], logger=Mock()
    )
    cog = AdminCog(bot)

    with patch(
        "rbb_bot.cogs.admin_cog.GuildDataService.reconcile_departed_guilds",
        new=AsyncMock(return_value=[3]),
    ) as reconcile_departed_guilds:
        await AdminCog.reconcile_guilds.callback(cog, ctx)

    reconcile_departed_guilds.assert_awaited_once_with([1, 2])
    ctx.send.assert_awaited_once_with("Marked 1 legacy departed guild.")
    bot.logger.info.assert_called_once_with(
        "Legacy guild reconciliation complete count=%s guild_ids=%s", 1, "3"
    )
