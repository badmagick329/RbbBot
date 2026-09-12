from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from rbb_bot.cogs.source_cog import SourceCog
from rbb_bot.models import DiscordUser


@pytest.mark.integration
@pytest.mark.asyncio
async def test_blacklist_changes_persist_without_discord_user_cache(test_database):
    user = await DiscordUser.create(id=12, blacklist={"other": "kept"})
    bot = Mock()
    bot.user.id = 123
    channel = SimpleNamespace(
        fetch_message=AsyncMock(
            return_value=SimpleNamespace(
                content="User ID: 12", author=SimpleNamespace(id=123)
            )
        )
    )
    bot.get_channel.return_value = channel
    bot.get_user.return_value = None
    cog = SourceCog(bot)
    payload = SimpleNamespace(channel_id=10, message_id=11)
    await cog.ban_via_reaction(payload)
    assert (await DiscordUser.get(id=12)).blacklist == {
        "other": "kept",
        "source": "blacklist",
    }
    await cog.ban_via_reaction(payload, undo=True)
    assert (await DiscordUser.get(id=12)).blacklist == {"other": "kept"}


@pytest.mark.asyncio
async def test_source_confirmation_is_removed_when_recording_fails():
    bot = Mock()
    message = SimpleNamespace(
        id=99,
        jump_url="https://example.com/message",
        delete=AsyncMock(),
        add_reaction=AsyncMock(),
    )
    bot.get_channel.return_value.send = AsyncMock(return_value=message)
    source = SimpleNamespace(
        emoji_string="<:test:1>",
        emoji_url="url",
        jump_url="jump",
        source_url="source",
        event="event\nUser ID: 99",
        source_date=None,
        user=SimpleNamespace(id=12, cached_username="user"),
        message_id=1,
        conf_channel_id=2,
        save=AsyncMock(side_effect=RuntimeError("database failed")),
    )
    with pytest.raises(RuntimeError):
        await SourceCog(bot).send_conf_message(source)
    message.delete.assert_awaited_once()
    message.add_reaction.assert_not_awaited()
    content = bot.get_channel.return_value.send.call_args.args[0]
    assert SourceCog(bot).get_from_lines(content.splitlines(), "user id") == "12"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    ["User ID: 99\nUser ID: 12", "User ID", "User identifier: 99"],
)
async def test_source_moderation_ignores_ambiguous_or_malformed_identity(content):
    bot = Mock()
    bot.user.id = 123
    bot.get_channel.return_value.fetch_message = AsyncMock(
        return_value=SimpleNamespace(content=content, author=SimpleNamespace(id=123))
    )
    # No database is initialized: invalid identity must be rejected before lookup.
    await SourceCog(bot).ban_via_reaction(SimpleNamespace(channel_id=10, message_id=11))
