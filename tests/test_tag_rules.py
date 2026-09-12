import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rbb_bot.domain.tags.rules import (
    TagDefinition,
    TagResponse,
    GuildTags,
    match_tag,
    normalize_trigger,
    normalize_response,
)
from rbb_bot.infrastructure.tags.catalog import CachedTagCatalog
from rbb_bot.application.tags.select_response import SelectTagResponse


def tag(id, trigger, inline=False):
    return TagDefinition(id, trigger, inline, (TagResponse(id, "reply"),))


def test_exact_match_wins_over_earlier_inline_tag():
    tags = (tag(1, "hello", True), tag(2, "hello there"))
    assert match_tag(tags, "  HELLO THERE ").id == 2
    assert match_tag(tags, "say hello now").id == 1


@pytest.mark.parametrize(
    "trigger,content,expected",
    [
        ("c++", "c++ is literal", True),
        ("c++", "cxx is not", False),
        ("hello", "helloworld", False),
        ("hello", "(hello)", True),
        ("hi", "this", False),
        ("hello", "hello_world", False),
    ],
)
def test_inline_matching_is_literal_with_word_boundaries(trigger, content, expected):
    assert (match_tag((tag(1, trigger, True),), content) is not None) == expected


def test_empty_tag_is_not_selected_and_ties_follow_order():
    empty = TagDefinition(1, "hello", False, ())
    assert (
        match_tag((empty, tag(2, "hello", True), tag(3, "hello", True)), "hello").id
        == 2
    )


@pytest.mark.parametrize(
    "normalize,value",
    [
        (normalize_trigger, "  "),
        (normalize_trigger, "a" * 201),
        (normalize_response, "  "),
        (normalize_response, "a" * 2001),
    ],
)
def test_invalid_tag_input_is_rejected(normalize, value):
    with pytest.raises(ValueError):
        normalize(value)


@pytest.mark.asyncio
async def test_invalidation_during_load_does_not_restore_stale_snapshot():
    started = asyncio.Event()
    resume = asyncio.Event()
    old = GuildTags(None, (tag(1, "old"),))
    new = GuildTags(None, (tag(1, "new"),))

    async def read(_):
        started.set()
        await resume.wait()
        return old

    repo = SimpleNamespace(snapshot=AsyncMock(side_effect=read))
    cache = CachedTagCatalog(repo)
    loading = asyncio.create_task(cache.get(1))
    await started.wait()
    cache.invalidate(1)
    repo.snapshot.side_effect = None
    repo.snapshot.return_value = new
    resume.set()
    assert await loading == new
    assert await cache.get(1) == new
    assert repo.snapshot.await_count == 2


@pytest.mark.asyncio
async def test_opt_out_prevents_cache_access_and_accounting():
    catalog = SimpleNamespace(get=AsyncMock())
    repo = SimpleNamespace(record_use=AsyncMock())
    selected = SelectTagResponse(
        catalog,
        repo,
        SimpleNamespace(is_opted_out=lambda _: True),
        lambda items: items[0],
    )
    assert await selected.execute(1, 2, 3, "hello") is None
    catalog.get.assert_not_awaited()
    repo.record_use.assert_not_awaited()
