from contextlib import nullcontext
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from rbb_bot.application.releases.contracts import ReleaseFilter, ReleaseListing
from rbb_bot.application.releases.lookup import (
    FindVideos,
    ListReleases,
    SearchTermMissing,
)
from rbb_bot.cogs.kpop_cog import KpopCog
from rbb_bot.views.releases import ReleasesView, VideoList

pytestmark = pytest.mark.asyncio

TODAY = date(2026, 11, 13)


def listing(
    released,
    artist="TWICE",
    title="Title",
    album_title="Album",
    release_type="Single",
    urls=(),
    release_time=None,
):
    return ReleaseListing(
        artist, title, album_title, release_type, released, release_time, tuple(urls)
    )


class FakeCatalogue:
    """In-memory releases, matched the way the release repository's contract states."""

    def __init__(self, *releases):
        self.releases = list(releases)

    async def search(self, criteria, *, on_or_after=None, before=None, newest_first):
        def contains(value, term):
            return not term or term.lower() in value.lower()

        found = [
            r
            for r in self.releases
            if contains(r.artist, criteria.artist)
            and contains(r.title, criteria.title)
            and (
                contains(r.title, criteria.title_or_album)
                or contains(r.album_title, criteria.title_or_album)
            )
            and contains(r.release_type, criteria.release_type)
            and (on_or_after is None or r.release_date >= on_or_after)
            and (before is None or r.release_date < before)
        ]
        return tuple(sorted(found, key=lambda r: r.release_date, reverse=newest_first))


def list_releases(*releases):
    return ListReleases(FakeCatalogue(*releases), today=lambda: TODAY)


async def test_videos_need_an_artist_or_a_release_name():
    with pytest.raises(SearchTermMissing):
        await FindVideos(FakeCatalogue()).execute(None, None)


async def test_videos_list_every_link_newest_release_first_and_skip_releases_without_links():
    older = listing(date(2026, 1, 1), urls=["a1", "a2"])
    unlinked = listing(date(2026, 2, 1))
    newer = listing(date(2026, 3, 1), urls=["b1"])
    other_artist = listing(date(2026, 4, 1), artist="IVE", urls=["c1"])

    videos = await FindVideos(
        FakeCatalogue(older, unlinked, newer, other_artist)
    ).execute("twice", None)

    assert videos == (("b1", newer), ("a1", older), ("a2", older))


async def test_videos_match_the_release_name_against_the_title_only():
    release = listing(date(2026, 1, 1), title="Other", album_title="Fancy", urls=["x"])

    catalogue = FakeCatalogue(release)

    assert await FindVideos(catalogue).execute(None, "fancy") == ()
    assert await FindVideos(catalogue).execute(None, "other") == (("x", release),)


async def test_releases_start_two_days_ago_oldest_first():
    too_old = listing(TODAY - timedelta(days=3))
    recent = listing(TODAY - timedelta(days=2))
    upcoming = listing(TODAY + timedelta(days=7))

    found = await list_releases(upcoming, too_old, recent).execute(ReleaseFilter())

    assert found.releases == (recent, upcoming)
    assert not found.showing_older


async def test_without_recent_releases_older_ones_follow_newest_first():
    oldest = listing(date(2026, 10, 1))
    older = listing(date(2026, 11, 5))

    found = await list_releases(oldest, older).execute(ReleaseFilter())

    assert found.releases == (older, oldest)
    assert found.showing_older


async def test_a_requested_start_date_replaces_the_window_and_never_falls_back():
    before_start = listing(date(2026, 11, 30))
    from_start = listing(date(2026, 12, 1))
    releases = list_releases(before_start, from_start)

    found = await releases.execute(
        ReleaseFilter(), start=date(2026, 12, 1), start_requested=True
    )
    assert found.releases == (from_start,)

    nothing = await releases.execute(
        ReleaseFilter(), start=date(2027, 1, 1), start_requested=True
    )
    assert nothing.releases == () and not nothing.showing_older


async def test_an_unreadable_start_date_keeps_the_default_window_without_fallback():
    older = listing(date(2026, 11, 5))

    found = await list_releases(older).execute(ReleaseFilter(), start_requested=True)

    assert found.releases == () and not found.showing_older


async def test_release_name_matches_the_album_title_too():
    by_album = listing(TODAY, title="Song", album_title="Fancy You")
    unrelated = listing(TODAY, title="Song", album_title="Other")

    found = await list_releases(by_album, unrelated).execute(
        ReleaseFilter(title_or_album="fancy")
    )

    assert found.releases == (by_album,)


def kpop_cog(*releases):
    return SimpleNamespace(
        bot=SimpleNamespace(logger=Mock()),
        scraper=SimpleNamespace(updating=False),
        repository=FakeCatalogue(*releases),
    )


def context():
    return SimpleNamespace(typing=nullcontext, send=AsyncMock())


async def test_comebacks_announce_the_fallback_before_the_older_releases():
    older = listing(date.today() - timedelta(days=30), title="Old song")
    ctx = context()

    await KpopCog.comebacks.callback(kpop_cog(older), ctx)

    first, second = ctx.send.call_args_list
    assert first.args == ("No recent releases found. Showing older releases",)
    assert "Old song" in second.kwargs["embed"].fields[1].value


async def test_comebacks_say_when_nothing_matches():
    ctx = context()
    await KpopCog.comebacks.callback(kpop_cog(), ctx)
    ctx.send.assert_awaited_once_with("No releases found")

    ctx = context()
    await KpopCog.comebacks.callback(kpop_cog(), ctx, start_date="2026-01-01")
    ctx.send.assert_awaited_once_with("No releases found.")


async def test_videos_command_asks_for_a_search_term():
    ctx = context()
    await KpopCog.videos.callback(kpop_cog(), ctx, None, None)
    ctx.send.assert_awaited_once_with(
        "Please provide an artist or a release name to search for."
    )


async def test_release_embed_shows_date_title_album_type_and_short_links():
    release = listing(
        date(2026, 11, 11),
        urls=["https://www.youtube.com/watch?v=abcdefghijk", "https://example.com/a"],
    )

    embed = ReleasesView(Mock(), [release]).create_embed([release])

    assert embed.fields[0].name == "1 release"
    assert embed.fields[1].name == "2026-11-11"
    assert embed.fields[1].value.startswith(
        "`TWICE`\nTitle (Album)\n*[Single]*\n"
        "https://youtu.be/abcdefghijk\nhttps://example.com/a"
    )


async def test_video_list_shows_the_release_time_or_date():
    timed = listing(
        date(2026, 11, 11),
        release_time=datetime(2026, 11, 11, 9, tzinfo=timezone.utc),
    )
    dated = listing(date(2026, 11, 12))
    items = [("https://v/1", timed), ("https://v/2", dated)]

    message = VideoList(Mock(), items, chunk_size=2).create_message(items)

    assert "<t:1794387600:f>\nTWICE - Title\nhttps://v/1" in message
    assert "**2026-11-12**\nTWICE - Title\nhttps://v/2" in message
