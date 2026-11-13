from datetime import date, datetime, timezone

import pytest

from rbb_bot.application.releases.contracts import ReleaseFilter, ReleaseListing
from rbb_bot.application.releases.lookup import FindVideos, ListReleases
from rbb_bot.infrastructure.releases.repository import ReleaseRepository
from rbb_bot.models import Artist, Release, ReleaseType

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def seed():
    twice = await Artist.create(name="TWICE")
    ive = await Artist.create(name="IVE")
    single = await ReleaseType.create(name="Single")
    album = await ReleaseType.create(name="Mini Album")
    await Release.create(
        artist=twice,
        release_type=single,
        title="Fancy",
        album_title="Fancy You",
        release_date=date(2026, 11, 1),
        release_time=datetime(2026, 11, 1, 9, tzinfo=timezone.utc),
        urls=["https://youtu.be/aaaaaaaaaaa"],
    )
    await Release.create(
        artist=twice,
        release_type=album,
        title="Strategy",
        album_title="Ten",
        release_date=date(2026, 12, 1),
        urls=None,
    )
    await Release.create(
        artist=ive,
        release_type=single,
        title="Rebel Heart",
        album_title="Empathy",
        release_date=date(2026, 10, 1),
        urls=[],
    )


async def titles(**kwargs):
    criteria = kwargs.pop("criteria", ReleaseFilter())
    found = await ReleaseRepository().search(criteria, **kwargs)
    return [release.title for release in found]


async def test_search_maps_rows_to_listings(test_database):
    await seed()

    found = await ReleaseRepository().search(
        ReleaseFilter(artist="twi"), newest_first=False
    )

    assert found == (
        ReleaseListing(
            "TWICE",
            "Fancy",
            "Fancy You",
            "Single",
            date(2026, 11, 1),
            datetime(2026, 11, 1, 9, tzinfo=timezone.utc),
            ("https://youtu.be/aaaaaaaaaaa",),
        ),
        ReleaseListing(
            "TWICE", "Strategy", "Ten", "Mini Album", date(2026, 12, 1), None, ()
        ),
    )


async def test_search_filters_partially_and_case_insensitively(test_database):
    await seed()

    assert await titles(newest_first=True) == ["Strategy", "Fancy", "Rebel Heart"]
    assert await titles(criteria=ReleaseFilter(title="fan"), newest_first=True) == [
        "Fancy"
    ]
    assert (
        await titles(criteria=ReleaseFilter(title="empathy"), newest_first=True) == []
    )
    assert await titles(
        criteria=ReleaseFilter(title_or_album="EMPATHY"), newest_first=True
    ) == ["Rebel Heart"]
    assert await titles(
        criteria=ReleaseFilter(release_type="mini"), newest_first=True
    ) == ["Strategy"]
    assert await titles(
        criteria=ReleaseFilter(artist="twice", title_or_album="ten"), newest_first=True
    ) == ["Strategy"]
    assert await titles(criteria=ReleaseFilter(artist=""), newest_first=False) == [
        "Rebel Heart",
        "Fancy",
        "Strategy",
    ]


async def test_search_bounds_the_release_date(test_database):
    await seed()

    assert await titles(on_or_after=date(2026, 11, 1), newest_first=False) == [
        "Fancy",
        "Strategy",
    ]
    assert await titles(before=date(2026, 11, 1), newest_first=True) == ["Rebel Heart"]


async def test_lookups_through_postgres(test_database):
    await seed()
    repository = ReleaseRepository()

    videos = await FindVideos(repository).execute("twice", None)
    assert [url for url, _ in videos] == ["https://youtu.be/aaaaaaaaaaa"]

    later = await ListReleases(repository, today=lambda: date(2027, 1, 1)).execute(
        ReleaseFilter(artist="twice")
    )
    assert [r.title for r in later.releases] == ["Strategy", "Fancy"]
    assert later.showing_older
