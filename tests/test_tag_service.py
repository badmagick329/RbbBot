import pytest

from rbb_bot.models import Guild, Response, Tag
from rbb_bot.services.tag_service import TagService


pytestmark = pytest.mark.integration


async def add_tag(guild, trigger: str, response: str, *, inline: bool = False):
    tag = await Tag.create(guild=guild, trigger=trigger, inline=inline)
    saved_response = await Response.create(guild=guild, content=response)
    await tag.responses.add(saved_response)
    return tag


@pytest.mark.asyncio
async def test_tag_service_matches_exact_before_inline_and_updates_use_count(
    test_database,
):
    guild = await Guild.create(id=1)
    inline = await add_tag(guild, "hello", "inline", inline=True)
    exact = await add_tag(guild, "hello there", "exact")
    service = TagService()
    await service.refresh_guild(guild.id)

    matched = service.match(guild.id, 10, "  HELLO THERE ")

    assert matched is not None
    assert matched.id == exact.id
    assert await service.choose_response(matched) == "exact"
    await exact.refresh_from_db()
    assert exact.use_count == 1
    assert service.match(guild.id, 10, "say hello now").id == inline.id


@pytest.mark.asyncio
async def test_tag_service_treats_inline_punctuation_as_literal(test_database):
    guild = await Guild.create(id=1)
    tag = await add_tag(guild, "c++", "literal", inline=True)
    service = TagService()
    await service.refresh_guild(guild.id)

    assert service.match(guild.id, 10, "c++ is literal").id == tag.id
    assert service.match(guild.id, 10, "cxx is not") is None


@pytest.mark.asyncio
async def test_tag_service_refresh_and_emoji_channel_exclusion(test_database):
    guild = await Guild.create(id=1, emojis_channel_id=99)
    await add_tag(guild, "hello", "first")
    service = TagService()
    await service.refresh_guild(guild.id)

    assert service.match(guild.id, 99, "hello") is None
    assert service.match(guild.id, 10, "hello") is not None

    await add_tag(guild, "bye", "second")
    assert service.match(guild.id, 10, "bye") is None
    await service.refresh_guild(guild.id)
    assert service.match(guild.id, 10, "bye") is not None
    service.remove_guild(guild.id)
    assert service.match(guild.id, 10, "hello") is None
