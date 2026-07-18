import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from rbb_bot.services.tag_service import CachedTag, GuildTagSnapshot
from rbb_bot.services.user_data_service import UserDataService


sys.path.insert(0, str(Path(__file__).parents[1] / "rbb_bot"))
from rbb_bot.cogs.tags_cog import TagsCog


class ContentMustNotBeRead:
    @property
    def content(self):
        raise AssertionError("message content must not be read for opted-out users")


@pytest.mark.asyncio
async def test_opted_out_tag_listener_never_reads_message_content():
    bot = SimpleNamespace(logger=Mock())
    cog = TagsCog(bot)
    message = ContentMustNotBeRead()
    message.author = SimpleNamespace(id=1, bot=False)
    message.guild = SimpleNamespace(id=1)
    message.channel = SimpleNamespace(id=1)
    previous = UserDataService._tag_opt_out_ids
    UserDataService._tag_opt_out_ids = {1}

    try:
        await cog.on_message(message)
    finally:
        UserDataService._tag_opt_out_ids = previous


@pytest.mark.asyncio
async def test_tag_listener_uses_cached_snapshot_without_orm_lookup():
    channel = SimpleNamespace(id=10, send=AsyncMock())
    bot = SimpleNamespace(
        logger=Mock(),
        get_context=AsyncMock(return_value=SimpleNamespace(invoked_with=None)),
    )
    cog = TagsCog(bot)
    cog.tag_service._guilds[1] = GuildTagSnapshot(
        emojis_channel_id=None,
        tags=(CachedTag(id=1, trigger="hello", inline=False, responses=("reply",)),),
    )
    message = SimpleNamespace(
        author=SimpleNamespace(id=1, bot=False),
        guild=SimpleNamespace(id=1),
        channel=channel,
        content="hello",
    )

    with patch.object(
        cog.tag_service, "choose_response", new=AsyncMock(return_value="reply")
    ):
        await cog.on_message(message)

    bot.get_context.assert_awaited_once_with(message)
    channel.send.assert_awaited_once_with("reply")
