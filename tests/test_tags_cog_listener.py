import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from rbb_bot.domain.tags.rules import TagDefinition, TagResponse, GuildTags
from rbb_bot.infrastructure.privacy.user_data import UserDataService


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
    cog.catalog._guilds[1] = GuildTags(
        emojis_channel_id=None,
        tags=(
            TagDefinition(
                id=1,
                trigger="hello",
                inline=False,
                responses=(TagResponse(1, "reply"),),
            ),
        ),
    )
    message = SimpleNamespace(
        author=SimpleNamespace(id=1, bot=False),
        guild=SimpleNamespace(id=1),
        channel=channel,
        content="hello",
    )

    with patch.object(cog.select_response.repository, "record_use", new=AsyncMock()):
        await cog.on_message(message)

    bot.get_context.assert_awaited_once_with(message)
    channel.send.assert_awaited_once_with("reply")


@pytest.mark.asyncio
async def test_invalid_tag_input_uses_existing_command_error_path():
    from discord.ext import commands

    cog = TagsCog(SimpleNamespace(logger=Mock()))
    ctx = SimpleNamespace(interaction=None, guild=SimpleNamespace(id=1))
    with pytest.raises(commands.BadArgument, match="Trigger can't be empty"):
        await TagsCog.add_.callback(cog, ctx, "  ", "reply")


@pytest.mark.asyncio
async def test_commands_are_not_interpreted_as_tags():
    bot = SimpleNamespace(
        logger=Mock(),
        get_context=AsyncMock(return_value=SimpleNamespace(invoked_with="tag")),
    )
    cog = TagsCog(bot)
    cog.select_response.execute = AsyncMock()
    message = ContentMustNotBeRead()
    message.author = SimpleNamespace(id=9876, bot=False)
    message.guild = SimpleNamespace(id=1)
    await cog.on_message(message)
    cog.select_response.execute.assert_not_awaited()
