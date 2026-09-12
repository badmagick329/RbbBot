import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest
from discord.ext import commands

from rbb_bot.cogs.emojis_cog import EmojisCog
from rbb_bot.cogs.logging_cog import LoggingCog
from rbb_bot.cogs.hangman_cog import HangmanCog
from rbb_bot.cogs.meme_cog import MemeCog
from rbb_bot.cogs.source_cog import SourceCog
from rbb_bot.domain.hangman import HangmanGame
from rbb_bot.views.guild_logging import message_event
from rbb_bot.views.hangman import HangmanView
from rbb_bot.settings.const import BotEmojis


@pytest.mark.asyncio
@pytest.mark.parametrize("cog_type", [EmojisCog, LoggingCog])
async def test_privileged_children_require_permissions_when_invoked_directly(cog_type):
    ctx = SimpleNamespace(guild=object(), permissions=discord.Permissions.none())
    for command in cog_type.__cog_commands__:
        if command.parent is None:
            continue
        with pytest.raises(commands.MissingPermissions):
            for check in command.checks:
                await discord.utils.maybe_coroutine(check, ctx)
        ctx.permissions = discord.Permissions.all()
        for check in command.checks:
            assert await discord.utils.maybe_coroutine(check, ctx)
        ctx.permissions = discord.Permissions.none()


def test_long_deleted_message_is_a_binary_utf8_attachment():
    message = SimpleNamespace(
        id=1,
        content="é" * 1500,
        created_at=datetime.now(timezone.utc),
        edited_at=None,
        author=SimpleNamespace(
            name="member",
            id=2,
            display_avatar=SimpleNamespace(url="https://example.com/avatar"),
        ),
        channel=SimpleNamespace(mention="<#3>"),
    )
    payload = message_event(message)
    try:
        assert message.content.encode("utf-8") in payload["file"].fp.read()
    finally:
        payload["file"].close()


@pytest.mark.asyncio
async def test_logging_cache_miss_fetches_channel_without_changing_settings():
    bot = Mock()
    bot.get_channel.return_value = None
    channel = SimpleNamespace(send=AsyncMock())
    bot.fetch_channel = AsyncMock(return_value=channel)
    cog = LoggingCog(bot)
    cog.configuration.channel_for = AsyncMock(return_value=12)
    await cog._send(1, "member_join", lambda: {"content": "joined"})
    bot.fetch_channel.assert_awaited_once_with(12)
    channel.send.assert_awaited_once_with(content="joined")


def test_hangman_counts_unique_letters_and_separates_same_name_players():
    game = HangmanGame("APPLE")
    assert game.guess(1, "same", "A")
    assert not game.guess(2, "same", "A")
    assert game.guess(2, "same", "P")
    assert game.guesses == {1: ["A"], 2: ["P"]}
    game.guess(1, "same", "L")
    game.guess(2, "same", "E")
    assert game.over and game.won
    assert not game.guess(1, "same", "X")


@pytest.mark.asyncio
async def test_hangman_finish_stops_timeout_and_releases_channel_even_if_edit_fails():
    finished = Mock()
    view = HangmanView("APPLE", finished)
    view.message = SimpleNamespace(
        edit=AsyncMock(side_effect=RuntimeError("deleted message"))
    )
    with pytest.raises(RuntimeError):
        await view.finish("Game ended")
    assert view.is_finished() and view.game.over
    finished.assert_called_once_with(view)
    assert all(button.disabled for button in view.children)


@pytest.mark.asyncio
async def test_hangman_keeps_every_player_within_discord_message_limit():
    word = "ABCDEFGHIJKLMNOPQRSTUVWXY"
    view = HangmanView(word, Mock())
    for player_id, letter in enumerate(word):
        view.game.guess(player_id, "_" * 30 + str(player_id).zfill(2), letter)
    message = view.create_message()
    assert len(message) <= 2000
    assert message.count("% correct") == 25
    assert f"You won! The word was {word}" in message
    view.close_game()


@pytest.mark.asyncio
async def test_failed_hangman_send_does_not_leave_channel_occupied():
    cog = HangmanCog(Mock())
    ctx = SimpleNamespace(
        defer=AsyncMock(),
        channel=SimpleNamespace(id=1),
        send=AsyncMock(side_effect=RuntimeError("send failed")),
    )
    with pytest.raises(RuntimeError):
        await HangmanCog.start_game.callback(cog, ctx)
    assert cog.ongoing_games == {}


@pytest.mark.asyncio
async def test_meme_file_is_removed_when_discord_send_fails(tmp_path):
    path = tmp_path / "meme.gif"
    path.write_bytes(b"GIF89a")
    ctx = SimpleNamespace(
        typing=Mock(), send=AsyncMock(side_effect=RuntimeError("send failed"))
    )
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock(return_value=False)
    with pytest.raises(RuntimeError):
        await MemeCog(Mock()).create_and_send(
            ctx, SimpleNamespace(create=AsyncMock(return_value=path)), "text"
        )
    assert not path.exists()


@pytest.mark.asyncio
async def test_source_moderation_rejects_nonowners_and_missing_member_payloads():
    cog = SourceCog(Mock())
    cog.delete_via_reaction = AsyncMock()
    cog.ban_via_reaction = AsyncMock()
    with patch(
        "rbb_bot.cogs.source_cog.get_discord_settings",
        return_value=SimpleNamespace(confirmation_channel_id=3, owner_id=1),
    ):
        for member in [None, SimpleNamespace(bot=False)]:
            payload = SimpleNamespace(
                member=member,
                channel_id=3,
                user_id=2,
                emoji=SimpleNamespace(name=BotEmojis.CROSS),
            )
            await cog.on_raw_reaction_add(payload)
        payload.emoji.name = BotEmojis.HAMMER
        await cog.on_raw_reaction_remove(payload)
    cog.delete_via_reaction.assert_not_awaited()
    cog.ban_via_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_delayed_emoji_post_respects_channel_disabled_during_wait():
    from discord.utils import utcnow

    cog = EmojisCog(Mock())
    cog.post_datetimes[1] = utcnow()
    cog.post_emojis = AsyncMock()
    with patch(
        "rbb_bot.cogs.emojis_cog.Guild.get_or_none",
        new=AsyncMock(return_value=SimpleNamespace(emojis_channel_id=None)),
    ):
        await cog.post_updated_emojis(SimpleNamespace(id=1), Mock())
    cog.post_emojis.assert_not_awaited()
    assert cog.post_datetimes == {}
