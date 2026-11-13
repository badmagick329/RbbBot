from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from rbb_bot.cogs.admin_cog import AdminCog


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
    ctx.send.assert_awaited_once_with("Marked 1 legacy departed server.")
    bot.logger.info.assert_called_once_with(
        "Legacy guild reconciliation complete count=%s guild_ids=%s", 1, "3"
    )


@pytest.mark.asyncio
async def test_privacy_status_contains_only_counts_and_state():
    ctx = SimpleNamespace(send=AsyncMock())
    bot = SimpleNamespace(logger=Mock())
    cog = AdminCog(bot)

    with patch(
        "rbb_bot.cogs.admin_cog.UserDataService.status",
        new=AsyncMock(
            return_value={
                "exists": True,
                "reminder_count": 2,
                "source_entry_count": 3,
                "tag_opt_out": True,
                "has_blacklist": True,
            }
        ),
    ):
        await AdminCog.privacy_status.callback(cog, ctx, 123)

    sent = ctx.send.await_args.args[0]
    assert "reminders=2" in sent
    assert "source_entries=3" in sent
    assert "text" not in sent
    assert "url" not in sent
