from datetime import date

import pytest

from rbb_bot.application.sources.contracts import (
    PublishedPost,
    RecordedSource,
    SourceDetails,
    SourceSubmission,
    Submitter,
    SubmitterTally,
)
from rbb_bot.application.sources.lookup import FindSource
from rbb_bot.application.sources.submit import SubmitSource
from rbb_bot.infrastructure.sources.repository import TortoiseSourceRepository
from rbb_bot.models import DiscordUser, SourceEntry
from tests.test_sources import FakeEmoteImages, FakePosts, accepting, request

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

EMOTE = "<:wave:123>"


def submission(user_id, details, emote=EMOTE):
    return SourceSubmission(
        emote,
        "https://cdn.discordapp.com/emojis/123.webp",
        details,
        1,
        2,
        3,
        "https://discord.com/channels/1/2/3",
        Submitter(user_id, None, False),
    )


async def test_registering_creates_the_user_and_caches_only_a_missing_name(
    test_database,
):
    repo = TortoiseSourceRepository()
    await DiscordUser.create(id=13, blacklist={"source": "blacklist"})

    assert await repo.register_submitter(12, "fan") == Submitter(12, "fan", False)
    assert await repo.register_submitter(12, "renamed") == Submitter(12, "fan", False)
    assert await repo.register_submitter(13, "late") == Submitter(13, "late", True)
    stored = await DiscordUser.get(id=13)
    assert stored.cached_username == "late"
    assert stored.blacklist == {"source": "blacklist"}


async def test_submissions_round_trip_encrypted_and_ordered_by_post(test_database):
    repo = TortoiseSourceRepository()
    await repo.register_submitter(12, "fan")
    await repo.register_submitter(13, "other")
    late = SourceDetails(None, "Inkigayo", None)
    early = SourceDetails("https://a.co/1", None, date(2024, 1, 1))

    await repo.record(submission(13, late), PublishedPost(20, "jump-20"))
    await repo.record(submission(12, early), PublishedPost(10, "jump-10"))
    await repo.record(submission(12, early, "<:other:9>"), PublishedPost(30, "jump-30"))

    assert await repo.exists(EMOTE)
    assert not await repo.exists("<:missing:1>")
    assert await repo.sources(EMOTE) == (
        RecordedSource(early, 12, "fan"),
        RecordedSource(late, 13, "other"),
    )
    stored = await SourceEntry.get(conf_message_id=10)
    assert stored.conf_jump_url == "jump-10"
    assert "wave" not in stored.emoji_string_ciphertext
    assert await repo.tallies() == (
        SubmitterTally(13, "other", 1),
        SubmitterTally(12, "fan", 2),
    )

    await repo.forget(10)
    assert await SourceEntry.filter(conf_message_id=10).exists() is False
    assert await SourceEntry.all().count() == 2


async def test_blacklist_changes_keep_other_features_entries(test_database):
    repo = TortoiseSourceRepository()
    await DiscordUser.create(id=12, cached_username="fan", blacklist={"other": "kept"})

    assert await repo.blacklisted(99) is None
    assert await repo.lift_blacklist(99) is False
    assert await repo.blacklisted(12) is False
    await repo.blacklist(12)
    assert await repo.blacklisted(12) is True
    assert (await DiscordUser.get(id=12)).blacklist == {
        "other": "kept",
        "source": "blacklist",
    }
    assert await repo.lift_blacklist(12) is True
    assert await repo.lift_blacklist(12) is False
    stored = await DiscordUser.get(id=12)
    assert stored.blacklist == {"other": "kept"}
    assert stored.cached_username == "fan"


async def test_submitting_through_postgres_is_found_by_emote(test_database):
    repo = TortoiseSourceRepository()
    use_case = SubmitSource(repo, FakeEmoteImages(), FakePosts(), logger=None)

    await use_case.add(request(event="Show", source_date="240101"), accepting())
    await use_case.edit(
        request(
            source_url="https://example.com/better",
            submitter_id=13,
            submitter_name="other",
        ),
        accepting(),
    )

    lookup = await FindSource(repo).execute("<:wave:123>")
    assert lookup.source_url == "https://example.com/better"
    assert lookup.event == "Show"
    assert lookup.source_date == date(2024, 1, 1)
    assert lookup.submitter_names == ("fan", "other")
