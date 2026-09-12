from rbb_bot.application.tags.contracts import TagSelector
from rbb_bot.infrastructure.tags.repository import TortoiseTagRepository
import pytest


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_guild_tags_and_responses_persist(test_database):
    from rbb_bot.models import Guild, Response, Tag

    assert await Guild.all().count() == 0

    guild = await Guild.create(id=1234)
    response = await Response.create(guild=guild, content="Hello from a tag")
    tag = await Tag.create(guild=guild, trigger="hello", inline=True)
    await tag.responses.add(response)

    saved_tag = await TortoiseTagRepository().find_tag(
        TagSelector(guild.id, trigger="hello")
    )
    assert saved_tag is not None

    assert guild.prefix == "!"
    assert saved_tag.inline is True
    assert [saved_response.content for saved_response in saved_tag.responses] == [
        "Hello from a tag"
    ]
