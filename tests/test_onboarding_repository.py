import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rbb_bot.infrastructure.member_onboarding.repository import (
    TortoiseOnboardingRepository,
)
from rbb_bot.application.member_onboarding.configure_greeting import (
    ConfigureGreeting,
    UpdateGreeting,
)
from rbb_bot.application.member_onboarding.welcome_messages import (
    ConfigureWelcomeMessages,
)
from rbb_bot.domain.member_onboarding.configuration import OnboardingInputError
from rbb_bot.models import Guild, Greeting, JoinEvent, JoinResponse, AutoRole

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_greeting_merge_preserves_encrypted_storage(test_database):
    repo = TortoiseOnboardingRepository()
    configure = ConfigureGreeting(
        repo, SimpleNamespace(channel_exists=AsyncMock(return_value=True))
    )
    await configure.set_channel(1, 99)
    await configure.execute(
        UpdateGreeting(1, "Custom {username}", "Hello {mention}", False)
    )
    settings = await configure.execute(UpdateGreeting(1, description="Changed"))
    assert settings.channel_id == 99
    assert settings.template.title == "Custom {username}"
    row = await Greeting.get()
    assert row.description == "Changed"
    assert row.description_ciphertext != "Changed"
    assert row.title_ciphertext != row.title


async def test_reads_are_non_destructive_and_invalid_update_rolls_back(test_database):
    repo = TortoiseOnboardingRepository()
    assert (await repo.greeting(1)).template is None
    assert (await repo.welcome(1)).messages == ()
    assert await Guild.all().count() == 0
    with pytest.raises(OnboardingInputError):
        await repo.update_greeting(1, "x" * 156, None, True)
    assert await Guild.all().count() == 0
    assert await Greeting.all().count() == 0


async def test_existing_welcome_links_load_and_mutations_remain_guild_scoped(
    test_database,
):
    repo = TortoiseOnboardingRepository()
    guild = await Guild.create(id=1)
    event = await JoinEvent.create(guild=guild, _channel_id=99)
    row = await JoinResponse.create(event=event, content="existing encrypted message")
    await event._responses.add(row)
    assert (await repo.welcome(1)).messages[0].content == row.content
    configure = ConfigureWelcomeMessages(
        repo, SimpleNamespace(channel_exists=AsyncMock(return_value=True))
    )
    added = await configure.add(1, ("existing encrypted message", "new", "new"))
    assert added == 1
    assert await JoinResponse.all().count() == 2
    assert not await configure.remove(2, row.id, None)
    await configure.set_channel(1, None)
    assert await configure.remove(1, row.id, None) == 1
    assert await configure.clear(1) == 1
    assert (await repo.welcome(1)).messages == ()
    assert await JoinResponse.all().count() == 0


async def test_concurrent_welcome_adds_deduplicate(test_database):
    repo = TortoiseOnboardingRepository()
    await repo.set_welcome_channel(1, 99)
    counts = await asyncio.gather(
        repo.add_messages(1, ("same",)), repo.add_messages(1, ("same",))
    )
    assert sorted(counts) == [0, 1]
    assert await JoinResponse.all().count() == 1


async def test_auto_role_limit_is_atomic_and_duplicate_does_not_consume_slot(
    test_database,
):
    repo = TortoiseOnboardingRepository()
    for role_id in range(4):
        assert await repo.add_role(1, role_id)
    results = await asyncio.gather(
        repo.add_role(1, 4), repo.add_role(1, 5), return_exceptions=True
    )
    assert sum(result is True for result in results) == 1
    assert sum(isinstance(result, OnboardingInputError) for result in results) == 1
    assert not await repo.add_role(1, 0)
    assert await AutoRole.filter(guild_id=1).count() == 5
    assert await repo.remove_roles(2, (0,)) == 0
    assert await repo.remove_roles(1, (0,)) == 1
