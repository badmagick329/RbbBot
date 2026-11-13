from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from rbb_bot.application.guild_prefixes.contracts import PrefixRefused, Refusal
from rbb_bot.application.guild_prefixes.prefixes import (
    LoadGuildPrefixes,
    ManageGuildPrefix,
)
from rbb_bot.cogs.guild_cog import GuildCog
from rbb_bot.domain.guild_prefixes import MAX_PREFIX_LENGTH

pytestmark = pytest.mark.asyncio

GUILD = 1


class FakeRepository:
    def __init__(self, stored=None, default="!"):
        self.stored = dict(stored or {})
        self.default = default
        self.reads = []

    async def prefix(self, guild_id):
        self.reads.append(guild_id)
        return self.stored.setdefault(guild_id, self.default)

    async def set_prefix(self, guild_id, prefix):
        self.stored[guild_id] = prefix

    async def all_prefixes(self):
        return dict(self.stored)


async def test_reading_returns_the_stored_prefix():
    manage = ManageGuildPrefix(FakeRepository({GUILD: "?"}), {})

    assert await manage.read(GUILD) == "?"


async def test_setting_stores_the_prefix_and_updates_the_parsing_map():
    repository = FakeRepository({GUILD: "!"})
    prefixes = {}

    await ManageGuildPrefix(repository, prefixes).set(GUILD, "?")

    assert repository.stored[GUILD] == "?"
    assert prefixes == {GUILD: "?"}


async def test_a_prefix_of_exactly_the_limit_is_accepted():
    repository = FakeRepository()

    await ManageGuildPrefix(repository, {}).set(GUILD, "x" * MAX_PREFIX_LENGTH)

    assert repository.stored[GUILD] == "x" * MAX_PREFIX_LENGTH


async def test_a_too_long_prefix_is_refused_but_the_guild_is_still_read():
    repository = FakeRepository()
    prefixes = {}

    with pytest.raises(PrefixRefused) as refused:
        await ManageGuildPrefix(repository, prefixes).set(
            GUILD, "x" * (MAX_PREFIX_LENGTH + 1)
        )

    assert refused.value.refusal is Refusal.TOO_LONG
    # Reading creates the configured-guild row, as the command always did.
    assert repository.reads == [GUILD]
    assert repository.stored == {GUILD: "!"}
    assert prefixes == {}


async def test_setting_the_current_prefix_is_refused():
    repository = FakeRepository({GUILD: "?"})
    prefixes = {}

    with pytest.raises(PrefixRefused) as refused:
        await ManageGuildPrefix(repository, prefixes).set(GUILD, "?")

    assert refused.value.refusal is Refusal.ALREADY_SET
    assert prefixes == {}


async def test_loading_fills_the_parsing_map_with_every_stored_prefix():
    prefixes = {}

    await LoadGuildPrefixes(FakeRepository({1: "?", 2: "$"}), prefixes).execute()

    assert prefixes == {1: "?", 2: "$"}


def cog_with(repository, prefixes):
    bot = SimpleNamespace(logger=Mock(), guild_prefixes=prefixes)
    cog = GuildCog(bot)
    cog.prefixes = ManageGuildPrefix(repository, prefixes)
    return cog


def context():
    return SimpleNamespace(
        interaction=None, guild=SimpleNamespace(id=GUILD), send=AsyncMock()
    )


@pytest.mark.parametrize(
    "new_prefix, reply",
    [
        (None, "Current prefix: !"),
        ("!", "Prefix is already set to !"),
        (
            "x" * (MAX_PREFIX_LENGTH + 1),
            f"Prefix must be less than {MAX_PREFIX_LENGTH} characters",
        ),
        ("?", "Setting prefix to ?"),
    ],
)
async def test_prefix_command_replies(new_prefix, reply):
    prefixes = {}
    cog = cog_with(FakeRepository({GUILD: "!"}), prefixes)
    ctx = context()

    await GuildCog.prefix.callback(cog, ctx, new_prefix)

    ctx.send.assert_awaited_once_with(reply)
    assert prefixes == ({GUILD: "?"} if new_prefix == "?" else {})
