from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rbb_bot.application.releases.refresh import RefreshReleases
from rbb_bot.infrastructure.releases.repository import ReleaseRepository
from rbb_bot.models import Artist, Release, ReleaseType


@pytest.mark.asyncio
async def test_refresh_combines_multiple_sources_before_one_save():
    store = SimpleNamespace(
        read=AsyncMock(return_value=[{"release_date": "2026-08-01", "title": "old"}]),
        save=AsyncMock(),
    )
    source = SimpleNamespace(
        read=AsyncMock(
            side_effect=[
                [{"release_date": "2026-09-01", "title": "first"}],
                [{"release_date": "2026-10-01", "title": "second"}],
            ]
        )
    )
    await RefreshReleases(source, store).execute(["one", "two"])
    saved = store.save.call_args.args[0]
    assert [row["title"] for row in saved] == ["old", "first", "second"]
    store.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_failure_of_later_source_leaves_database_untouched():
    store = SimpleNamespace(read=AsyncMock(return_value=[]), save=AsyncMock())
    source = SimpleNamespace(
        read=AsyncMock(
            side_effect=[
                [{"release_date": "2026-09-01"}],
                RuntimeError("remote failed"),
            ]
        )
    )
    with pytest.raises(RuntimeError):
        await RefreshReleases(source, store).execute(["one", "two"])
    store.save.assert_not_awaited()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_release_replacement_rolls_back_deletion_if_insert_fails(
    test_database, monkeypatch
):
    artist = await Artist.create(name="Artist")
    kind = await ReleaseType.create(name="Single")
    existing = await Release.create(
        artist=artist,
        release_type=kind,
        title="Keep me",
        album_title="Album",
        release_date="2026-09-01",
    )
    monkeypatch.setattr(
        Release, "bulk_create", AsyncMock(side_effect=RuntimeError("insert failed"))
    )
    row = {
        "id": None,
        "artist": "New artist",
        "release_type": "EP",
        "title": "New",
        "album_title": "New album",
        "release_date": "2026-09-01",
        "release_time": None,
        "urls": [],
        "reddit_urls": [],
    }
    with pytest.raises(RuntimeError):
        await ReleaseRepository().save([row])
    assert await Release.filter(id=existing.id, title="Keep me").exists()
    assert not await Artist.filter(name="New artist").exists()
    assert not await ReleaseType.filter(name="EP").exists()
