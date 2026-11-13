from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from rbb_bot.application.guild_lifecycle.cleanup import CleanupExpiredGuilds
from rbb_bot.application.guild_lifecycle.membership import (
    RecordGuildDeparture,
    RecordGuildRejoin,
)
from rbb_bot.cogs.guild_cog import GuildCog
from rbb_bot.infrastructure.guild_lifecycle.confirmation_posts import (
    GuildConfirmationPosts,
)
from rbb_bot.infrastructure.sources.confirmation import SourceConfirmationService

pytestmark = pytest.mark.asyncio


class FakeLifecycle:
    """Departed guilds keyed by ID; a value is that guild's source entries."""

    def __init__(self, expired=None, configured=(), departed=()):
        self.expired = dict(expired or {})
        self.configured = set(configured) | set(self.expired) | set(departed)
        self.departed = set(departed) | set(self.expired)
        self.deleted = []
        self.refuse_delete = set()
        self.ineligible = set()
        self.failing = set()

    async def record_departure(self, guild_id):
        if guild_id in self.failing:
            raise RuntimeError("database down")
        if guild_id not in self.configured or guild_id in self.departed:
            return False
        self.departed.add(guild_id)
        return True

    async def record_rejoin(self, guild_id):
        if guild_id in self.failing:
            raise RuntimeError("database down")
        if guild_id not in self.departed:
            return False
        self.departed.discard(guild_id)
        return True

    async def expired_cleanup_candidates(self):
        return list(self.expired)

    async def source_entries_for_cleanup(self, guild_id):
        if guild_id in self.failing:
            raise RuntimeError("database down")
        if guild_id in self.ineligible:
            return None
        return self.expired[guild_id]

    async def delete_guild_data(self, guild_id):
        if guild_id in self.refuse_delete:
            return False
        self.deleted.append(guild_id)
        return True


class FakeConfirmationPosts:
    def __init__(self, failing=()):
        self.failing = set(failing)
        self.deleted = []

    async def delete(self, guild_id, source_entries):
        if guild_id in self.failing:
            return False
        self.deleted.append((guild_id, source_entries))
        return True


def cleanup(lifecycle, posts=None, logger=None, on_deleted=None):
    return CleanupExpiredGuilds(
        lifecycle,
        posts or FakeConfirmationPosts(),
        logger or Mock(),
        on_deleted or (lambda guild_id: None),
    )


async def test_cleanup_deletes_confirmation_posts_then_guild_data():
    lifecycle = FakeLifecycle({1: ["entry"]})
    posts = FakeConfirmationPosts()
    logger = Mock()
    deleted = []

    result = await cleanup(lifecycle, posts, logger, deleted.append).execute()

    assert result == [1]
    assert posts.deleted == [(1, ["entry"])]
    assert lifecycle.deleted == [1]
    assert deleted == [1]
    logger.info.assert_called_once_with(
        "Guild cleanup complete count=%s guild_ids=%s", 1, "1"
    )


async def test_cleanup_keeps_a_guild_whose_confirmation_posts_survive():
    lifecycle = FakeLifecycle({1: ["entry"], 2: []})
    logger = Mock()
    deleted = []

    result = await cleanup(
        lifecycle, FakeConfirmationPosts(failing={1}), logger, deleted.append
    ).execute()

    assert result == [2]
    assert lifecycle.deleted == [2]
    assert deleted == [2]
    logger.info.assert_called_once_with(
        "Guild cleanup complete count=%s guild_ids=%s", 1, "2"
    )


async def test_cleanup_skips_a_guild_that_rejoined_before_its_entries_were_read():
    lifecycle = FakeLifecycle({1: ["entry"]})
    lifecycle.ineligible.add(1)
    posts = FakeConfirmationPosts()
    logger = Mock()

    assert await cleanup(lifecycle, posts, logger).execute() == []

    assert posts.deleted == []
    assert lifecycle.deleted == []
    logger.info.assert_not_called()


async def test_cleanup_warns_when_the_guild_rejoined_after_its_posts_were_deleted():
    lifecycle = FakeLifecycle({1: []})
    lifecycle.refuse_delete.add(1)
    logger = Mock()
    deleted = []

    assert await cleanup(lifecycle, None, logger, deleted.append).execute() == []

    assert deleted == []
    logger.warning.assert_called_once_with(
        "Guild cleanup skipped after source confirmation cleanup guild_id=%s", 1
    )


async def test_one_guild_failing_does_not_stop_the_others():
    lifecycle = FakeLifecycle({1: [], 2: []})
    lifecycle.failing.add(1)
    logger = Mock()

    assert await cleanup(lifecycle, None, logger).execute() == [2]

    logger.exception.assert_called_once_with("Guild cleanup failed guild_id=%s", 1)


async def test_a_failing_cache_callback_leaves_the_guild_out_of_the_report():
    lifecycle = FakeLifecycle({1: []})
    logger = Mock()

    def broken(guild_id):
        raise RuntimeError("cache")

    assert await cleanup(lifecycle, None, logger, broken).execute() == []

    logger.exception.assert_called_once_with("Guild cleanup failed guild_id=%s", 1)
    logger.info.assert_not_called()


async def test_departure_and_rejoin_log_only_state_changes():
    lifecycle = FakeLifecycle(configured={1})
    logger = Mock()
    depart = RecordGuildDeparture(lifecycle, logger)
    rejoin = RecordGuildRejoin(lifecycle, logger)

    await depart.execute(1)
    await depart.execute(1)
    await depart.execute(9999)
    await rejoin.execute(1)
    await rejoin.execute(1)

    assert lifecycle.departed == set()
    assert [c.args for c in logger.info.call_args_list] == [
        ("Guild marked departed guild_id=%s", 1),
        ("Guild departure state cleared guild_id=%s", 1),
    ]


async def test_departure_and_rejoin_failures_are_logged_not_raised():
    lifecycle = FakeLifecycle()
    lifecycle.failing.add(1)
    logger = Mock()

    await RecordGuildDeparture(lifecycle, logger).execute(1)
    await RecordGuildRejoin(lifecycle, logger).execute(1)

    assert [c.args for c in logger.exception.call_args_list] == [
        ("Guild departure lifecycle handling failed guild_id=%s", 1),
        ("Guild rejoin lifecycle handling failed guild_id=%s", 1),
    ]


def cog_with(lifecycle, bot=None):
    bot = bot or SimpleNamespace(logger=Mock(), guild_prefixes={})
    cog = GuildCog(bot)
    cog.record_departure = RecordGuildDeparture(lifecycle, bot.logger)
    cog.record_rejoin = RecordGuildRejoin(lifecycle, bot.logger)
    return cog


async def test_guild_listeners_track_departure_by_guild_id():
    lifecycle = FakeLifecycle(configured={1234})
    cog = cog_with(lifecycle)

    await cog.on_guild_remove(SimpleNamespace(id=1234))
    assert lifecycle.departed == {1234}

    await cog.on_guild_join(SimpleNamespace(id=1234))
    assert lifecycle.departed == set()


async def test_a_deleted_guild_leaves_the_prefix_map_and_tag_catalogue():
    catalog = Mock()
    bot = SimpleNamespace(
        logger=Mock(), guild_prefixes={1: "?", 2: "!"}, tag_catalog=catalog
    )
    cog = GuildCog(bot)
    lifecycle = FakeLifecycle({2: []})
    cog.cleanup = CleanupExpiredGuilds(
        lifecycle, FakeConfirmationPosts(), bot.logger, cog.guild_deleted
    )

    await GuildCog.guild_cleanup_task.coro(cog)

    assert bot.guild_prefixes == {1: "?"}
    catalog.invalidate.assert_called_once_with(2)


def confirmation_bot(channel):
    return SimpleNamespace(
        logger=Mock(), get_channel=Mock(return_value=channel), fetch_channel=AsyncMock()
    )


async def test_confirmation_posts_are_deleted_from_discord():
    message = SimpleNamespace(delete=AsyncMock())
    channel = SimpleNamespace(fetch_message=AsyncMock(return_value=message))
    posts = GuildConfirmationPosts(SourceConfirmationService(confirmation_bot(channel)))
    entry = SimpleNamespace(conf_channel_id=123, conf_message_id=456)

    assert await posts.delete(1, [entry]) is True

    channel.fetch_message.assert_awaited_once_with(456)
    message.delete.assert_awaited_once()


async def test_a_missing_confirmation_post_counts_as_deleted():
    not_found = discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"), "missing"
    )
    channel = SimpleNamespace(fetch_message=AsyncMock(side_effect=not_found))
    posts = GuildConfirmationPosts(SourceConfirmationService(confirmation_bot(channel)))
    entry = SimpleNamespace(conf_channel_id=123, conf_message_id=456)

    assert await posts.delete(1, [entry]) is True


async def test_a_forbidden_confirmation_post_blocks_cleanup_with_guild_scope():
    forbidden = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "missing access"
    )
    channel = SimpleNamespace(fetch_message=AsyncMock(side_effect=forbidden))
    bot = confirmation_bot(channel)
    posts = GuildConfirmationPosts(SourceConfirmationService(bot))
    entry = SimpleNamespace(conf_channel_id=123, conf_message_id=456)

    assert await posts.delete(1, [entry]) is False

    bot.logger.exception.assert_called_once_with(
        "Source confirmation deletion failed scope=%s scope_id=%s "
        "source_entry_count=%s",
        "guild",
        1,
        1,
    )
