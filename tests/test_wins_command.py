import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rbb_bot.application.wins.latest import RecordedWin, WinsUnavailable
from rbb_bot.cogs.kpop_cog import KpopCog
from rbb_bot.views.wins import wins_embed

WIN = RecordedWin(1, date(2026, 10, 18), "Music Bank", 2, "Song", 3, "artist", "Artist")


@pytest.mark.parametrize(
    "slash,artist,expected",
    [
        (True, None, None),
        (True, " TWICE ", "TWICE"),
        (False, "Akdong Musician", "Akdong Musician"),
    ],
)
def test_hybrid_invocation_defers_before_fetch(slash, artist, expected):
    async def scenario():
        events = []

        async def defer():
            events.append("defer")

        async def execute(value):
            events.append("fetch")
            assert value == expected
            return (WIN,)

        cog = SimpleNamespace(
            bot=SimpleNamespace(latest_wins=SimpleNamespace(execute=execute))
        )
        ctx = SimpleNamespace(
            interaction=object() if slash else None, defer=defer, send=AsyncMock()
        )
        await KpopCog.wins.callback(cog, ctx, artist=artist)
        assert events == (["defer", "fetch"] if slash else ["fetch"])
        kwargs = ctx.send.call_args.kwargs
        assert kwargs["allowed_mentions"].to_dict()["parse"] == []
        assert kwargs["embed"].fields[0].name.startswith("2026-10-18")

    asyncio.run(scenario())


@pytest.mark.parametrize("artist", [" ", "a" * 101, "a\nb"])
def test_invalid_input_is_useful_and_never_fetched(artist):
    async def scenario():
        execute = AsyncMock()
        cog = SimpleNamespace(
            bot=SimpleNamespace(latest_wins=SimpleNamespace(execute=execute))
        )
        ctx = SimpleNamespace(interaction=None, send=AsyncMock())
        await KpopCog.wins.callback(cog, ctx, artist=artist)
        execute.assert_not_awaited()
        assert "1–100" in ctx.send.call_args.args[0]
        assert "https://kpopwins.info/wins" in ctx.send.call_args.args[0]

    asyncio.run(scenario())


def test_failure_is_translated_but_programming_errors_escape():
    async def scenario():
        execute = AsyncMock(side_effect=WinsUnavailable("private internal exception"))
        cog = SimpleNamespace(
            bot=SimpleNamespace(latest_wins=SimpleNamespace(execute=execute))
        )
        ctx = SimpleNamespace(interaction=None, send=AsyncMock())
        await KpopCog.wins.callback(cog, ctx)
        assert (
            "temporarily unavailable" in ctx.send.call_args.kwargs["embed"].description
        )
        assert "private" not in str(ctx.send.call_args)
        execute.side_effect = RuntimeError("bug")
        with pytest.raises(RuntimeError):
            await KpopCog.wins.callback(cog, ctx)

    asyncio.run(scenario())


def test_renderer_links_dates_and_five_record_limit():
    embed = wins_embed((WIN,) * 6)
    assert embed.title == "Latest recorded wins"
    assert len(embed.fields) == 5
    assert embed.fields[0].name == "2026-10-18 · Music Bank"
    assert "https://kpopwins.info/artists/artist" in embed.fields[0].value
    assert "https://kpopwins.info/songs/2" in embed.fields[0].value
    assert "https://kpopwins.info/wins" in embed.description


def test_empty_unavailable_and_filter_titles():
    assert "No recorded wins matched" in wins_embed(artist="TWICE").description
    assert "for TWICE" in wins_embed(artist="TWICE").title
    failed = wins_embed(unavailable=True)
    assert "temporarily unavailable" in failed.description
    assert "No recorded" not in failed.description
    assert "https://kpopwins.info/wins" in failed.description


@pytest.mark.parametrize("artist", ["Artist", "An artist alias"])
def test_filtered_title_links_to_resolved_artist(artist):
    embed = wins_embed((WIN,), artist=artist)
    assert embed.url == "https://kpopwins.info/artists/artist"
    assert "[Browse the wins archive](https://kpopwins.info/wins)" in embed.description


def test_title_keeps_archive_for_unfiltered_empty_or_ambiguous_results():
    other = RecordedWin(2, WIN.date, "The Show", 4, "Song", 5, "other", "Other")
    for embed in (
        wins_embed((WIN,)),
        wins_embed(artist="Unknown"),
        wins_embed(artist="Artist", unavailable=True),
        wins_embed((WIN, other), artist="Shared alias"),
    ):
        assert embed.url == "https://kpopwins.info/wins"


def test_renderer_bounds_and_escapes_untrusted_text():
    text = "**[link](https://evil.test) @everyone <@123> \\" * 200
    win = RecordedWin(1, WIN.date, text, 2, text, 3, "safe-slug", text)
    embed = wins_embed((win,) * 5, artist=text)
    assert len(embed) <= 6000
    assert len(embed.title) <= 256
    for field in embed.fields:
        assert len(field.name) <= 256
        assert len(field.value) <= 1024
        assert "@everyone" not in field.value
        assert "<@123>" not in field.value
        assert r"\[link\]" in field.value
        assert "https://kpopwins.info/artists/safe-slug" in field.value


def test_command_registration_and_cooldown():
    command = KpopCog.wins
    assert command.app_command.name == "wins"
    assert command.clean_params["artist"].default is None
    assert command._buckets._cooldown.rate == 2
    assert command._buckets._cooldown.per == 5
    assert sum(c.name == "wins" for c in KpopCog.__cog_commands__) == 1
