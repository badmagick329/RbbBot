from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from rbb_bot.application.emotes.configure import ConfigureEmoteChannel
from rbb_bot.application.emotes.contracts import (
    ChannelAccess,
    EmoteChannelRefused,
    EmoteChannelSettings,
    EmoteChannelUnavailable,
    Refusal,
)
from rbb_bot.application.emotes.post_emotes import PostEmotesNow, RepostEmotes
from rbb_bot.cogs.emojis_cog import EmojisCog
from rbb_bot.domain.emotes import MAX_CHANNEL_MESSAGE
from rbb_bot.infrastructure.emotes.discord_poster import DiscordEmotePoster

pytestmark = pytest.mark.asyncio

GUILD = 1
CHANNEL = 7


class FakeRepository:
    def __init__(self, settings=EmoteChannelSettings()):
        self.stored = settings

    async def settings(self, guild_id):
        return self.stored

    async def assign(self, guild_id, channel_id, delete_previous):
        self.stored = EmoteChannelSettings(
            channel_id, self.stored.message, delete_previous
        )

    async def unassign(self, guild_id):
        self.stored = EmoteChannelSettings(
            None, self.stored.message, self.stored.delete_previous
        )

    async def set_message(self, guild_id, message):
        self.stored = EmoteChannelSettings(
            self.stored.channel_id, message, self.stored.delete_previous
        )


class FakePoster:
    def __init__(self, access=ChannelAccess(True, True), failure=None):
        self.granted = access
        self.failure = failure
        self.events = []

    async def access(self, channel_id):
        self.events.append(("access", channel_id))
        return self.granted

    async def post(self, channel_id, message, delete_previous):
        if self.failure is not None:
            raise self.failure
        self.events.append(("post", channel_id, message, delete_previous))


class RecordingNotices:
    def __init__(self):
        self.sent = []

    async def execute(self, guild_id, notice):
        self.sent.append((guild_id, notice))


def configured(channel_id=CHANNEL, message=None, delete_previous=True):
    return FakeRepository(EmoteChannelSettings(channel_id, message, delete_previous))


def http_error(kind, code=0):
    response = SimpleNamespace(
        status=403 if kind is discord.Forbidden else 404, reason="Refused"
    )
    return kind(response, {"code": code, "message": "Discord says no"})


# Configuring the emote channel


async def test_assigning_a_channel_stores_it_and_announces_the_change():
    repository = FakeRepository()
    changed = []
    configure = ConfigureEmoteChannel(repository, changed.append)

    await configure.assign(GUILD, CHANNEL, delete_previous=False)

    assert await configure.read(GUILD) == EmoteChannelSettings(CHANNEL, None, False)
    assert changed == [GUILD]


async def test_reassigning_the_same_channel_is_refused_and_changes_nothing():
    repository = configured(delete_previous=True)
    changed = []
    configure = ConfigureEmoteChannel(repository, changed.append)

    with pytest.raises(EmoteChannelRefused) as refused:
        await configure.assign(GUILD, CHANNEL, delete_previous=False)

    assert refused.value.refusal is Refusal.ALREADY_ASSIGNED
    assert repository.stored.delete_previous is True
    assert changed == []


async def test_unassigning_keeps_the_message_and_announces_the_change():
    repository = configured(message="Enjoy", delete_previous=False)
    changed = []

    await ConfigureEmoteChannel(repository, changed.append).unassign(GUILD)

    assert repository.stored == EmoteChannelSettings(None, "Enjoy", False)
    assert changed == [GUILD]


async def test_message_up_to_the_limit_is_stored_and_longer_is_refused():
    repository = configured()
    changed = []
    configure = ConfigureEmoteChannel(repository, changed.append)

    await configure.set_message(GUILD, "x" * MAX_CHANNEL_MESSAGE)
    with pytest.raises(EmoteChannelRefused) as refused:
        await configure.set_message(GUILD, "y" * (MAX_CHANNEL_MESSAGE + 1))

    assert refused.value.refusal is Refusal.MESSAGE_TOO_LONG
    assert repository.stored.message == "x" * MAX_CHANNEL_MESSAGE
    await configure.clear_message(GUILD)
    assert repository.stored.message is None
    assert changed == []


# Posting on request


async def test_posting_now_announces_the_channel_before_posting_its_settings():
    poster = FakePoster()

    async def announce(channel_id):
        poster.events.append(("announce", channel_id))

    await PostEmotesNow(configured(message="Enjoy"), poster).execute(GUILD, announce)

    assert poster.events == [
        ("access", CHANNEL),
        ("announce", CHANNEL),
        ("post", CHANNEL, "Enjoy", True),
    ]


@pytest.mark.parametrize(
    "repository,access,refusal",
    [
        (FakeRepository(), ChannelAccess(True, True), Refusal.NO_CHANNEL),
        (configured(), ChannelAccess(False, True), Refusal.MISSING_MANAGE_MESSAGES),
        (configured(), ChannelAccess(True, False), Refusal.MISSING_READ_HISTORY),
    ],
)
async def test_posting_now_is_refused_before_anything_is_posted(
    repository, access, refusal
):
    poster = FakePoster(access)
    announce = AsyncMock()

    with pytest.raises(EmoteChannelRefused) as refused:
        await PostEmotesNow(repository, poster).execute(GUILD, announce)

    assert refused.value.refusal is refusal
    announce.assert_not_awaited()
    assert not any(event[0] == "post" for event in poster.events)


async def test_posting_without_clearing_needs_no_clearing_permissions():
    poster = FakePoster(ChannelAccess(False, False))

    await PostEmotesNow(configured(delete_previous=False), poster).execute(
        GUILD, AsyncMock()
    )

    assert ("post", CHANNEL, None, False) in poster.events


# Reposting after emotes change


def repost(repository, poster, notices=None, logger=None):
    return RepostEmotes(
        repository,
        poster,
        notices if notices is not None else RecordingNotices(),
        logger if logger is not None else Mock(),
    )


async def test_repost_uses_the_settings_current_when_it_runs():
    poster = FakePoster()
    repository = configured(message="Enjoy")

    await repository.unassign(GUILD)
    await repost(repository, poster).execute(GUILD)

    assert poster.events == []


@pytest.mark.parametrize(
    "deleted,key,remedy",
    [
        (False, "emote-channel-forbidden:7", "Manage Messages"),
        (True, "emote-channel-deleted:7", "/emote post unassign"),
    ],
)
async def test_repost_into_unavailable_channel_warns_and_notifies_the_guild(
    deleted, key, remedy
):
    notices, logger = RecordingNotices(), Mock()
    poster = FakePoster(failure=EmoteChannelUnavailable(CHANNEL, deleted))

    await repost(configured(), poster, notices, logger).execute(GUILD)

    [(guild_id, notice)] = notices.sent
    assert guild_id == GUILD
    assert notice.key == key
    assert notice.identifiers == (("Channel ID", CHANNEL),)
    assert remedy in notice.remedy
    logger.warning.assert_called_once()
    assert logger.warning.call_args.args[1:] == (GUILD, CHANNEL)


async def test_repost_failure_the_guild_cannot_fix_propagates_without_notice():
    notices = RecordingNotices()
    poster = FakePoster(failure=RuntimeError("bug"))

    with pytest.raises(RuntimeError):
        await repost(configured(), poster, notices).execute(GUILD)

    assert notices.sent == []


# Discord adapter


class FakeEmote:
    def __init__(self, name, animated=False):
        self.name, self.animated = name, animated

    def __str__(self):
        return f"<{'a' if self.animated else ''}:{self.name}:1>"


class FakeChannel:
    def __init__(self, history=(), purge_error=None):
        self.sent = []
        self.purged = False
        self.previous = [SimpleNamespace(delete=AsyncMock()) for _ in history]
        self.purge_error = purge_error

    async def purge(self, limit):
        if self.purge_error is not None:
            raise self.purge_error
        self.purged = True

    async def history(self, limit):
        for message in self.previous:
            yield message

    async def send(self, content):
        self.sent.append(content)

    def permissions_for(self, member):
        return discord.Permissions(manage_messages=True, read_message_history=False)


def adapter(channel, emotes=(), cached=True):
    bot = SimpleNamespace(
        get_channel=lambda _: channel if cached else None,
        fetch_channel=AsyncMock(return_value=channel),
    )
    guild = SimpleNamespace(id=GUILD, emojis=list(emotes), me=object())
    return DiscordEmotePoster(bot, guild, emotes_per_message=2), bot


async def test_adapter_posts_static_then_animated_emotes_in_batches_then_the_message():
    channel = FakeChannel(history=[1, 2])
    emotes = [
        FakeEmote("a1", True),
        FakeEmote("s1"),
        FakeEmote("s2"),
        FakeEmote("s3"),
        FakeEmote("a2", True),
    ]
    poster, _ = adapter(channel, emotes)

    await poster.post(CHANNEL, "Enjoy", delete_previous=True)

    assert channel.purged
    assert all(message.delete.await_count == 1 for message in channel.previous)
    assert channel.sent == [
        "<:s1:1><:s2:1>",
        "<:s3:1>",
        "<a:a1:1><a:a2:1>",
        "Enjoy",
    ]


async def test_adapter_keeps_previous_posts_and_skips_an_empty_message():
    channel = FakeChannel(history=[1])
    poster, _ = adapter(channel, [FakeEmote("s1")])

    await poster.post(CHANNEL, None, delete_previous=False)

    assert not channel.purged
    channel.previous[0].delete.assert_not_awaited()
    assert channel.sent == ["<:s1:1>"]


async def test_adapter_fetches_an_uncached_channel_once_for_access_and_post():
    channel = FakeChannel()
    poster, bot = adapter(channel, cached=False)

    assert await poster.access(CHANNEL) == ChannelAccess(True, False)
    await poster.post(CHANNEL, None, delete_previous=False)

    bot.fetch_channel.assert_awaited_once_with(CHANNEL)


@pytest.mark.parametrize(
    "error,deleted",
    [
        (http_error(discord.Forbidden, 50013), False),
        (http_error(discord.NotFound, 10003), True),
    ],
)
async def test_adapter_reports_a_channel_the_guild_must_fix(error, deleted):
    poster, bot = adapter(None, cached=False)
    bot.fetch_channel.side_effect = error

    with pytest.raises(EmoteChannelUnavailable) as unavailable:
        await poster.post(CHANNEL, None, delete_previous=True)

    assert (unavailable.value.channel_id, unavailable.value.deleted) == (
        CHANNEL,
        deleted,
    )
    assert unavailable.value.__cause__ is error


async def test_adapter_lets_a_message_vanishing_mid_purge_through():
    channel = FakeChannel(purge_error=http_error(discord.NotFound, 10008))
    poster, _ = adapter(channel)

    with pytest.raises(discord.NotFound):
        await poster.post(CHANNEL, None, delete_previous=True)


# Cog


def cog_with(repository, bot=None):
    cog = EmojisCog(bot if bot is not None else Mock())
    cog.repository = cog.configure.repository = repository
    return cog


def context():
    guild = SimpleNamespace(id=GUILD, emojis=[], me=object())
    return SimpleNamespace(interaction=None, guild=guild, send=AsyncMock())


def sent(ctx):
    return [call.args[0] for call in ctx.send.await_args_list]


async def test_assigning_through_the_cog_refreshes_the_tag_catalogue():
    bot = SimpleNamespace(tag_catalog=Mock())
    cog = cog_with(FakeRepository(), bot)
    ctx = context()
    channel = SimpleNamespace(id=CHANNEL, mention=f"<#{CHANNEL}>")

    await EmojisCog.assign.callback(cog, ctx, channel, True)
    await EmojisCog.assign.callback(cog, ctx, channel, True)
    await EmojisCog.unassign.callback(cog, ctx)

    assert sent(ctx) == [
        "Assigned <#7> to post emotes in",
        "This channel is already assigned as the emotes channel",
        "Unassigned the channel emotes are posted in",
    ]
    assert bot.tag_catalog.invalidate.call_count == 2


async def test_setting_the_message_through_the_cog():
    repository = configured()
    cog = cog_with(repository)
    ctx = context()

    await EmojisCog.set_message.callback(cog, ctx, message="Enjoy")
    await EmojisCog.set_message.callback(cog, ctx, message="x" * 2001)
    assert repository.stored.message == "Enjoy"
    await EmojisCog.set_message.callback(cog, ctx, message=" Clear ")

    assert sent(ctx) == [
        "Message set",
        "Message is too long. Max length is 2000",
        "Cleared the message",
    ]
    assert repository.stored.message is None


def post_now_cog(channel, settings=None, bot=None):
    bot = bot or SimpleNamespace(get_channel=lambda _: channel, send_error=AsyncMock())
    return cog_with(settings or configured(delete_previous=False), bot)


async def test_post_now_announces_then_posts_into_the_channel():
    channel = FakeChannel()
    cog = post_now_cog(channel, configured(message="Enjoy", delete_previous=False))
    ctx = context()

    await EmojisCog.post_now.callback(cog, ctx)

    assert sent(ctx) == ["Posting emotes in <#7>"]
    assert channel.sent == ["Enjoy"]


async def test_post_now_explains_a_refusal():
    cog = post_now_cog(FakeChannel(), FakeRepository())
    ctx = context()

    await EmojisCog.post_now.callback(cog, ctx)

    assert sent(ctx) == ["No channel assigned to post emotes in"]


async def test_post_now_into_a_forbidden_channel_tells_the_requester():
    channel = FakeChannel()
    channel.send = AsyncMock(side_effect=http_error(discord.Forbidden, 50013))
    cog = post_now_cog(channel)
    ctx = context()
    ctx.guild.emojis = [FakeEmote("s1")]

    await EmojisCog.post_now.callback(cog, ctx)

    assert sent(ctx)[-1] == "I do not have permission to post in the assigned channel"
    cog.bot.send_error.assert_not_awaited()


async def test_post_now_reports_other_posting_failures_to_the_owner():
    channel = FakeChannel(purge_error=http_error(discord.NotFound, 10008))
    channel.permissions_for = lambda member: discord.Permissions.all()
    cog = post_now_cog(channel, configured(delete_previous=True))
    ctx = context()

    await EmojisCog.post_now.callback(cog, ctx)

    assert sent(ctx) == ["Posting emotes in <#7>"]
    cog.bot.send_error.assert_awaited_once()


async def test_post_now_leaves_failures_before_posting_to_the_command_error_handler():
    bot = SimpleNamespace(
        get_channel=lambda _: None,
        fetch_channel=AsyncMock(side_effect=http_error(discord.Forbidden, 50001)),
        send_error=AsyncMock(),
    )
    cog = post_now_cog(None, bot=bot)
    ctx = context()

    with pytest.raises(discord.Forbidden):
        await EmojisCog.post_now.callback(cog, ctx)

    assert sent(ctx) == []
    bot.send_error.assert_not_awaited()


async def test_emote_changes_schedule_one_repost_per_guild_with_a_channel():
    cog = cog_with(configured(), SimpleNamespace(logger=Mock()))
    guild = SimpleNamespace(id=GUILD)

    await cog.on_guild_emojis_update(guild, [], [])
    await cog.on_guild_emojis_update(guild, [], [])
    try:
        assert len(cog.post_tasks) == 1
        assert set(cog.post_datetimes) == {GUILD}
    finally:
        await cog.cog_unload()

    unconfigured = cog_with(FakeRepository(), SimpleNamespace(logger=Mock()))
    await unconfigured.on_guild_emojis_update(guild, [], [])
    assert unconfigured.post_tasks == set()
