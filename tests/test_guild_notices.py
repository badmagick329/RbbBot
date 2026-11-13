import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest
from discord.utils import utcnow

from rbb_bot.application.guild_logging.configure import LoggingSettings
from rbb_bot.application.guild_logging.report_notice import (
    LogChannelUnavailable,
    ReportGuildNotice,
)
from rbb_bot.application.member_onboarding.contracts import (
    GreetingSettings,
    WelcomeSettings,
)
from rbb_bot.application.member_onboarding.handle_member_join import (
    MemberJoinAction,
    MemberJoinFailure,
)
from rbb_bot.application.member_onboarding.join_notices import join_failure_notice
from rbb_bot.cogs.emojis_cog import EmojisCog
from rbb_bot.cogs.logging_cog import LoggingCog
from rbb_bot.cogs.member_onboarding_cog import MemberOnboardingCog
from rbb_bot.domain.guild_logging import GuildNotice
from rbb_bot.domain.member_onboarding.configuration import DEFAULT_GREETING
from rbb_bot.infrastructure.guild_logging.notice_channel import DiscordNoticeChannel
from rbb_bot.infrastructure.member_onboarding.discord_actions import DiscordOnboarding
from rbb_bot.views.guild_logging import guild_notice

pytestmark = pytest.mark.asyncio

HOUR = 60 * 60


class FakeLoggingRepository:
    def __init__(self, channel_id=None):
        self.settings = LoggingSettings(channel_id=channel_id)

    async def read(self, guild_id):
        return self.settings

    async def update(self, guild_id, changes):
        raise AssertionError("Reporting a notice must not change logging settings")


class RecordingNoticeChannel:
    def __init__(self, unavailable=False):
        self.posts = []
        self.unavailable = unavailable

    async def post(self, channel_id, notice):
        if self.unavailable:
            raise LogChannelUnavailable(channel_id)
        self.posts.append((channel_id, notice))


class RecordingLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, msg, *args):
        self.warnings.append(msg % args)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeOnboardingRepository:
    def __init__(self, greeting_channel=None, welcome_channel=None, role_ids=()):
        self.greeting_channel = greeting_channel
        self.welcome_channel = welcome_channel
        self.ids = role_ids

    async def greeting(self, guild_id):
        return GreetingSettings(
            self.greeting_channel,
            DEFAULT_GREETING if self.greeting_channel else None,
        )

    async def welcome(self, guild_id):
        return WelcomeSettings(None, ())

    async def role_ids(self, guild_id):
        return self.ids

    async def remove_roles(self, guild_id, ids):
        return 0


class FakeRole:
    def __init__(self, id, position):
        self.id, self.position, self.managed = id, position, False
        self.name = f"Role {id}"

    def is_default(self):
        return False

    def __lt__(self, other):
        return self.position < other.position


def notice(key="problem"):
    return GuildNotice(key, "Something failed.", "Fix it.", (("Channel ID", 5),))


def reporter(channel_id=77, channel=None, logger=None, clock=None):
    return ReportGuildNotice(
        FakeLoggingRepository(channel_id),
        channel if channel is not None else RecordingNoticeChannel(),
        logger if logger is not None else RecordingLogger(),
        clock if clock is not None else FakeClock(),
    )


def http_error(kind, code=0, text="Discord says no"):
    response = SimpleNamespace(
        status=403 if kind is discord.Forbidden else 404, reason="Refused"
    )
    return kind(response, {"code": code, "message": text})


def rendered(notice):
    return json.dumps(guild_notice(notice).to_dict())


def new_member(guild):
    return SimpleNamespace(
        id=2,
        bot=False,
        roles=[],
        guild=guild,
        name="member",
        mention="<@2>",
        display_avatar="https://example.com/avatar.png",
    )


def guild_without_manage_roles():
    return SimpleNamespace(
        id=1,
        roles=[FakeRole(5, 1)],
        me=SimpleNamespace(
            guild_permissions=SimpleNamespace(manage_roles=False),
            top_role=FakeRole(9, 10),
        ),
    )


async def test_join_with_missing_manage_roles_notifies_log_channel_with_ids_and_remedy():
    guild = guild_without_manage_roles()
    channel = RecordingNoticeChannel()
    bot = SimpleNamespace(
        get_guild=lambda _: guild,
        logger=Mock(),
        guild_notices=reporter(77, channel),
    )
    cog = MemberOnboardingCog(bot)
    cog.repository = FakeOnboardingRepository(role_ids=(5,))
    await cog.on_member_join(new_member(guild))

    [(channel_id, posted)] = channel.posts
    assert channel_id == 77
    assert ("Member ID", 2) in posted.identifiers
    assert ("Role ID", 5) in posted.identifiers
    assert "Manage Roles" in posted.remedy
    assert "/autorole remove" in posted.remedy
    assert bot.logger.log.call_args.args[0] == logging.WARNING


async def test_join_failure_the_guild_cannot_fix_stays_operational_only():
    channel = RecordingNoticeChannel()
    guild = guild_without_manage_roles()
    guild.member_count = 3
    bot = SimpleNamespace(
        get_channel=Mock(side_effect=RuntimeError("bug")),
        get_guild=lambda _: guild,
        logger=Mock(),
        guild_notices=reporter(77, channel),
    )
    cog = MemberOnboardingCog(bot)
    cog.repository = FakeOnboardingRepository(greeting_channel=12)
    await cog.on_member_join(new_member(guild))

    assert channel.posts == []
    [call] = bot.logger.log.call_args_list
    assert call.args[0] == logging.ERROR
    assert call.args[2] == MemberJoinAction.GREETING.value


async def test_guild_without_log_channel_gets_nothing_and_nothing_raises():
    channel = RecordingNoticeChannel()
    logger = RecordingLogger()
    await reporter(None, channel, logger).execute(1, notice())
    assert channel.posts == []
    assert logger.warnings == []


async def test_repeat_notice_is_suppressed_for_an_hour_then_sent_again():
    channel = RecordingNoticeChannel()
    clock = FakeClock()
    report = reporter(77, channel, clock=clock)

    await report.execute(1, notice())
    clock.now += HOUR - 1
    await report.execute(1, notice())
    await report.execute(1, notice("other problem"))
    await report.execute(2, notice())
    assert [(c, n.key) for c, n in channel.posts] == [
        (77, "problem"),
        (77, "other problem"),
        (77, "problem"),
    ]

    clock.now += 1
    await report.execute(1, notice())
    assert len(channel.posts) == 4


@pytest.mark.parametrize("failure", [discord.Forbidden, discord.NotFound])
async def test_inaccessible_log_channel_logs_ids_once_and_does_not_raise(failure):
    bot = SimpleNamespace(
        get_channel=lambda _: None,
        fetch_channel=AsyncMock(side_effect=http_error(failure)),
    )
    logger = RecordingLogger()
    report = reporter(77, DiscordNoticeChannel(bot), logger)

    await report.execute(1, notice("first"))
    await report.execute(1, notice("second"))

    assert logger.warnings == ["Guild log channel unavailable guild_id=1 channel_id=77"]


async def test_notice_renders_ids_and_remedy_into_the_log_channel():
    channel = SimpleNamespace(send=AsyncMock())
    bot = SimpleNamespace(get_channel=lambda _: channel)
    await DiscordNoticeChannel(bot).post(
        77, GuildNotice("k", "Problem.", "Remedy.", (("Role ID", 5), ("Role ID", 6)))
    )
    embed = channel.send.await_args.kwargs["embed"].to_dict()
    assert embed["description"] == "Problem."
    assert {"name": "Role ID", "value": "5, 6", "inline": True} in embed["fields"]
    assert embed["fields"][-1]["value"] == "Remedy."


async def test_notice_identifiers_reject_free_text():
    with pytest.raises(TypeError):
        GuildNotice("k", "Problem.", "Remedy.", (("Member", "member text"),))


async def test_notice_from_join_failure_carries_no_message_content_or_discord_text():
    channel = SimpleNamespace(
        send=AsyncMock(
            side_effect=http_error(discord.Forbidden, 50013, "secret discord text")
        )
    )
    adapter = DiscordOnboarding(SimpleNamespace(get_channel=lambda _: channel))
    with pytest.raises(Exception) as caught:
        await adapter.send_welcome(12, "secret welcome content")
    failure = MemberJoinFailure(
        MemberJoinAction.JOIN_RESPONSE, caught.value, caught.value.__traceback__
    )

    posted = join_failure_notice(failure, 2)

    assert posted is not None
    assert ("Channel ID", 12) in posted.identifiers
    text = rendered(posted)
    assert "secret welcome content" not in text
    assert "secret discord text" not in text


def channel_adapter(error):
    channel = SimpleNamespace(send=AsyncMock(side_effect=error))
    member = new_member(SimpleNamespace(member_count=3))
    return DiscordOnboarding(SimpleNamespace(get_channel=lambda _: channel), member)


def roles_adapter(error, manage_roles=True):
    member = SimpleNamespace(id=2, add_roles=AsyncMock(side_effect=error))
    guild = SimpleNamespace(
        me=SimpleNamespace(guild_permissions=SimpleNamespace(manage_roles=manage_roles))
    )
    return DiscordOnboarding(SimpleNamespace(get_guild=lambda _: guild), member)


@pytest.mark.parametrize(
    "action,call,expected",
    [
        (
            MemberJoinAction.GREETING,
            lambda: channel_adapter(http_error(discord.Forbidden)).send_greeting(
                12, DEFAULT_GREETING
            ),
            ("Embed Links in <#12>", "/greet enable"),
        ),
        (
            MemberJoinAction.GREETING,
            lambda: channel_adapter(http_error(discord.NotFound, 10003)).send_greeting(
                12, DEFAULT_GREETING
            ),
            ("/greet enable", "/greet disable"),
        ),
        (
            MemberJoinAction.JOIN_RESPONSE,
            lambda: channel_adapter(http_error(discord.Forbidden)).send_welcome(
                12, "hi"
            ),
            ("Send Messages in <#12>", "/welcome channel"),
        ),
        (
            MemberJoinAction.JOIN_RESPONSE,
            lambda: channel_adapter(http_error(discord.NotFound, 10003)).send_welcome(
                12, "hi"
            ),
            ("/welcome channel", "/welcome disable"),
        ),
        (
            MemberJoinAction.AUTO_ROLES,
            lambda: roles_adapter(http_error(discord.Forbidden)).apply_roles(
                1, 2, (5,)
            ),
            ("Manage Roles", "<@&5>", "/autorole remove"),
        ),
        (
            MemberJoinAction.AUTO_ROLES,
            lambda: roles_adapter(http_error(discord.NotFound, 10011)).apply_roles(
                1, 2, (5,)
            ),
            ("/autorole list",),
        ),
        (
            MemberJoinAction.AUTO_ROLES,
            lambda: roles_adapter(None, manage_roles=False).apply_roles(1, 2, (5,)),
            ("Manage Roles", "/autorole remove_all"),
        ),
    ],
)
async def test_guild_caused_join_failures_become_notices_with_remedy(
    action, call, expected
):
    with pytest.raises(Exception) as caught:
        await call()
    posted = join_failure_notice(
        MemberJoinFailure(action, caught.value, caught.value.__traceback__), 2
    )
    assert posted is not None
    assert ("Member ID", 2) in posted.identifiers
    for phrase in expected:
        assert phrase in posted.remedy


@pytest.mark.parametrize(
    "call",
    [
        # The member left before roles were applied.
        lambda: roles_adapter(http_error(discord.NotFound, 10007)).apply_roles(
            1, 2, (5,)
        ),
        lambda: roles_adapter(
            discord.HTTPException(SimpleNamespace(status=500, reason="Down"), "")
        ).apply_roles(1, 2, (5,)),
        lambda: roles_adapter(RuntimeError("bug")).apply_roles(1, 2, (5,)),
    ],
)
async def test_join_failures_the_guild_cannot_fix_produce_no_notice(call):
    with pytest.raises(Exception) as caught:
        await call()
    failure = MemberJoinFailure(
        MemberJoinAction.AUTO_ROLES, caught.value, caught.value.__traceback__
    )
    assert join_failure_notice(failure, 2) is None


@pytest.mark.parametrize("failure", [discord.Forbidden, discord.NotFound])
async def test_logging_listener_swallows_unavailable_log_channel(failure):
    logger = RecordingLogger()
    channel = SimpleNamespace(send=AsyncMock(side_effect=http_error(failure)))
    bot = SimpleNamespace(
        get_channel=lambda _: channel, guild_notices=reporter(logger=logger)
    )
    cog = LoggingCog(bot)
    cog.configuration.channel_for = AsyncMock(return_value=12)

    await cog._send(1, "message_removed", lambda: {"content": "secret content"})
    await cog._send(1, "message_removed", lambda: {"content": "secret content"})

    assert logger.warnings == ["Guild log channel unavailable guild_id=1 channel_id=12"]


def emote_cog(channel, notices):
    bot = SimpleNamespace(
        get_channel=lambda _: channel,
        logger=Mock(),
        guild_notices=reporter(77, notices),
    )
    cog = EmojisCog(bot)
    cog.post_datetimes[1] = utcnow()
    return cog


def emote_settings():
    return patch(
        "rbb_bot.cogs.emojis_cog.Guild.get_or_none",
        new=AsyncMock(
            return_value=SimpleNamespace(
                emojis_channel_id=7,
                emojis_channel_message=None,
                delete_emoji_messages=True,
            )
        ),
    )


@pytest.mark.parametrize(
    "error,expected",
    [
        (http_error(discord.Forbidden, 50013), "Manage Messages"),
        (http_error(discord.NotFound, 10003), "/emote post unassign"),
    ],
)
async def test_emote_repost_into_inaccessible_channel_notifies_guild(error, expected):
    notices = RecordingNoticeChannel()
    channel = SimpleNamespace(purge=AsyncMock(side_effect=error))
    cog = emote_cog(channel, notices)
    with emote_settings():
        await cog.post_updated_emojis(SimpleNamespace(id=1), Mock())

    [(channel_id, posted)] = notices.posts
    assert channel_id == 77
    assert posted.identifiers == (("Channel ID", 7),)
    assert expected in posted.remedy
    assert "/emote post assign" in posted.remedy
    cog.bot.logger.warning.assert_called_once()


async def test_emote_repost_message_vanishing_mid_purge_is_not_a_guild_notice():
    notices = RecordingNoticeChannel()
    channel = SimpleNamespace(
        purge=AsyncMock(side_effect=http_error(discord.NotFound, 10008))
    )
    cog = emote_cog(channel, notices)
    with emote_settings(), pytest.raises(discord.NotFound):
        await cog.post_updated_emojis(SimpleNamespace(id=1), Mock())
    assert notices.posts == []
