import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rbb_bot.application.tags.contracts import TagSelector
from rbb_bot.application.tags.manage_tags import (
    AddTag,
    AddTagRequest,
    RenameTag,
    RenameTagRequest,
    RemoveTag,
    RemoveResponses,
    ListTags,
)
from rbb_bot.application.tags.select_response import SelectTagResponse
from rbb_bot.domain.tags.rules import match_tag
from rbb_bot.infrastructure.tags.catalog import CachedTagCatalog
from rbb_bot.infrastructure.tags.repository import TortoiseTagRepository
from rbb_bot.models import Guild, Tag, Response

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def feature():
    repo = TortoiseTagRepository()
    cache = CachedTagCatalog(repo)
    return repo, cache, AddTag(repo, cache)


async def test_add_rename_and_delete_refresh_cached_matching(test_database):
    repo, cache, add = feature()
    assert (await cache.get(1)).tags == ()
    result = await add.execute(AddTagRequest(1, " HELLO ", " first "))
    assert result.status == "created"
    assert match_tag((await cache.get(1)).tags, "hello").id == result.tag.id
    duplicate = await add.execute(AddTagRequest(1, "hello", "first"))
    assert duplicate.status == "duplicate"
    assert await Response.all().count() == 1
    await add.execute(AddTagRequest(1, "hello", "second"))
    assert len((await cache.get(1)).tags[0].responses) == 2
    await RenameTag(repo, cache).execute(
        RenameTagRequest(1, result.tag.id, " GOODBYE ")
    )
    assert match_tag((await cache.get(1)).tags, "hello") is None
    assert match_tag((await cache.get(1)).tags, "goodbye").id == result.tag.id
    assert await RemoveTag(repo, cache).execute(1, result.tag.id)
    assert (await cache.get(1)).tags == ()
    assert await Response.all().count() == 0


async def test_encrypted_lookup_and_response_selection_keep_storage_and_count(
    test_database,
):
    repo, cache, add = feature()
    created = await add.execute(AddTagRequest(1, "hello", "private response"))
    stored = await Tag.get(id=created.tag.id)
    assert "hello" not in stored.trigger_ciphertext
    assert (await Response.first()).content_ciphertext != "private response"
    assert (await repo.find_tag(TagSelector(1, trigger=" HELLO "))).id == created.tag.id
    selected = SelectTagResponse(
        cache,
        repo,
        SimpleNamespace(is_opted_out=lambda _: False),
        lambda items: items[0],
    )
    assert await selected.execute(1, 10, 20, "hello") == "private response"
    await stored.refresh_from_db()
    assert stored.use_count == 1
    assert (await ListTags(repo).execute(1))[0].use_count == 1
    # Warm message handling needs no configuration reads.
    repo.snapshot = AsyncMock(side_effect=AssertionError("cache miss"))
    assert await selected.execute(1, 10, 20, "hello") == "private response"


async def test_emoji_channel_and_guild_removal_invalidate_cache(test_database):
    repo, cache, add = feature()
    await add.execute(AddTagRequest(1, "hello", "reply"))
    selected = SelectTagResponse(
        cache,
        repo,
        SimpleNamespace(is_opted_out=lambda _: False),
        lambda items: items[0],
    )
    assert await selected.execute(1, 99, 20, "hello") == "reply"
    await Guild.filter(id=1).update(emojis_channel_id=99)
    cache.invalidate(1)
    assert await selected.execute(1, 99, 20, "hello") is None
    await Guild.filter(id=1).delete()
    cache.invalidate(1)
    assert await selected.execute(1, 10, 20, "hello") is None


async def test_deleting_tag_preserves_shared_responses(test_database):
    repo, cache, add = feature()
    first = (await add.execute(AddTagRequest(1, "first", "shared"))).tag
    second = (await add.execute(AddTagRequest(1, "second", "own"))).tag
    second_row = await Tag.get(id=second.id)
    shared = await Response.get(id=first.responses[0].id)
    await second_row.responses.add(shared)
    assert await RemoveTag(repo, cache).execute(1, first.id)
    assert await Response.filter(id=shared.id).exists()
    remaining = await repo.find_tag(TagSelector(1, second.id))
    assert {r.content for r in remaining.responses} == {"shared", "own"}


async def test_response_deletion_is_scoped_and_removes_empty_tags(test_database):
    repo, cache, add = feature()
    first = (await add.execute(AddTagRequest(1, "first", "one"))).tag
    other = (await add.execute(AddTagRequest(2, "other", "two"))).tag
    await cache.get(1)
    count = await RemoveResponses(repo, cache).execute(
        1, (first.responses[0].id, other.responses[0].id)
    )
    assert count == 1
    assert (await cache.get(1)).tags == ()
    assert await repo.find_tag(TagSelector(2, other.id)) is not None
    assert not await RemoveTag(repo, cache).execute(1, other.id)
    assert (
        await RenameTag(repo, cache).execute(RenameTagRequest(1, other.id, "wrong"))
        is None
    )


async def test_concurrent_adds_deduplicate_response_and_rename_rejects_conflict(
    test_database,
):
    repo, cache, add = feature()
    await Guild.create(id=1)
    results = await asyncio.gather(
        *(add.execute(AddTagRequest(1, "hello", "reply")) for _ in range(2))
    )
    assert {r.status for r in results} == {"created", "duplicate"}
    assert await Tag.all().count() == 1
    other = (await add.execute(AddTagRequest(1, "other", "reply"))).tag
    with pytest.raises(ValueError, match="already exists"):
        await RenameTag(repo, cache).execute(RenameTagRequest(1, other.id, "hello"))
    assert (await repo.find_tag(TagSelector(1, other.id))).trigger == "other"


async def test_reads_do_not_create_guilds_or_delete_empty_tags(test_database):
    repo, cache, add = feature()
    assert await ListTags(repo).execute(99) == ()
    assert not await Guild.filter(id=99).exists()
    guild = await Guild.create(id=1)
    empty = await Tag.create(guild=guild, trigger="empty")
    assert (await ListTags(repo).execute(1))[0].responses == ()
    assert match_tag((await cache.get(1)).tags, "empty") is None
    assert await Tag.filter(id=empty.id).exists()
