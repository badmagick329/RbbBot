from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from rbb_bot.application.member_onboarding.auto_roles import (
    ConfigureAutoRoles,
    ApplyAutoRoles,
)
from rbb_bot.application.member_onboarding.contracts import (
    RoleInfo,
    MemberInfo,
    GreetingSettings,
    WelcomeSettings,
    WelcomeMessage,
)
from rbb_bot.application.member_onboarding.join_actions import ConfiguredJoinActions
from rbb_bot.application.member_onboarding.handle_member_join import (
    HandleMemberJoin,
    MemberJoinAction,
)
from rbb_bot.application.member_onboarding.welcome_messages import (
    ConfigureWelcomeMessages,
    ImportWelcomeUrls,
)
from rbb_bot.domain.member_onboarding.configuration import (
    DEFAULT_GREETING,
    greeting_template,
    OnboardingInputError,
)
from rbb_bot.infrastructure.member_onboarding.discord_actions import DiscordOnboarding

pytestmark = pytest.mark.asyncio


async def test_bulk_roles_skip_bots_and_existing_roles_and_continue_after_failure():
    configured = SimpleNamespace(
        available=AsyncMock(
            return_value=(RoleInfo(1, "valid", True), RoleInfo(2, "managed", False))
        )
    )
    gateway = SimpleNamespace(
        apply_roles=AsyncMock(side_effect=[RuntimeError("forbidden"), None])
    )
    members = (
        MemberInfo(10, True, frozenset()),
        MemberInfo(11, False, frozenset({1})),
        MemberInfo(12, False, frozenset()),
        MemberInfo(13, False, frozenset()),
    )
    result = await ApplyAutoRoles(configured, gateway).execute(1, members)
    assert result.applied_members == 1
    assert result.failures[0][0] == 12
    assert result.skipped_role_ids == (2,)
    assert [call.args for call in gateway.apply_roles.await_args_list] == [
        (1, 12, (1,)),
        (1, 13, (1,)),
    ]


async def test_deleted_roles_are_pruned_only_after_successful_resolution():
    repo = SimpleNamespace(
        role_ids=AsyncMock(return_value=(1, 2)), remove_roles=AsyncMock()
    )
    gateway = SimpleNamespace(
        roles=AsyncMock(side_effect=RuntimeError("Discord unavailable"))
    )
    configured = ConfigureAutoRoles(repo, gateway)
    with pytest.raises(RuntimeError):
        await configured.available(1)
    repo.remove_roles.assert_not_awaited()
    gateway.roles.side_effect = None
    gateway.roles.return_value = (RoleInfo(1, "existing", True),)
    assert len(await configured.available(1)) == 1
    repo.remove_roles.assert_awaited_once_with(1, (2,))


async def test_join_actions_do_not_let_missing_channel_block_roles():
    repo = SimpleNamespace(
        greeting=AsyncMock(return_value=GreetingSettings(99, DEFAULT_GREETING)),
        welcome=AsyncMock(
            return_value=WelcomeSettings(88, (WelcomeMessage(1, "hello"),))
        ),
    )
    gateway = SimpleNamespace(
        send_greeting=AsyncMock(side_effect=RuntimeError("deleted channel")),
        send_welcome=AsyncMock(),
    )
    roles = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(failures=(), skipped_role_ids=())
        )
    )
    actions = ConfiguredJoinActions(
        1,
        MemberInfo(2, False, frozenset()),
        repo,
        gateway,
        roles,
        lambda messages: messages[0],
    )
    failures = await HandleMemberJoin(actions).execute()
    assert [failure.action for failure in failures] == [MemberJoinAction.GREETING]
    gateway.send_welcome.assert_awaited_once_with(88, "hello")
    roles.execute.assert_awaited_once()


async def test_welcome_import_validates_all_urls_before_writing():
    repo = SimpleNamespace(add_messages=AsyncMock())
    welcome = ConfigureWelcomeMessages(repo, Mock())
    source = SimpleNamespace(
        urls=AsyncMock(return_value=("https://valid.example", "x" * 1901))
    )
    with pytest.raises(OnboardingInputError):
        await ImportWelcomeUrls(welcome, source).execute(1, 2, True)
    repo.add_messages.assert_not_awaited()


async def test_missing_channel_does_not_clear_assignment():
    repo = SimpleNamespace(
        welcome=AsyncMock(return_value=WelcomeSettings(99, ())),
        add_messages=AsyncMock(),
        set_welcome_channel=AsyncMock(),
    )
    gateway = SimpleNamespace(channel_exists=AsyncMock(return_value=False))
    with pytest.raises(OnboardingInputError, match="no longer exists"):
        await ConfigureWelcomeMessages(repo, gateway).add(1, ("hello",))
    repo.set_welcome_channel.assert_not_awaited()
    repo.add_messages.assert_not_awaited()


class FakeRole:
    def __init__(self, id, position, managed=False, default=False):
        self.id, self.position, self.managed, self.default = (
            id,
            position,
            managed,
            default,
        )
        self.name = f"Role {id}"

    def is_default(self):
        return self.default

    def __lt__(self, other):
        return self.position < other.position


@pytest.mark.parametrize(
    "permissions,managed,default,position,expected",
    [
        (True, False, False, 1, True),
        (False, False, False, 1, False),
        (True, True, False, 1, False),
        (True, False, True, 1, False),
        (True, False, False, 10, False),
    ],
)
async def test_role_permissions_and_hierarchy(
    permissions, managed, default, position, expected
):
    role = FakeRole(2, position, managed, default)
    guild = SimpleNamespace(
        roles=[role],
        me=SimpleNamespace(
            guild_permissions=SimpleNamespace(manage_roles=permissions),
            top_role=FakeRole(3, 10),
        ),
    )
    result = await DiscordOnboarding(SimpleNamespace(get_guild=lambda _: guild)).roles(
        1, (2,)
    )
    assert result[0].assignable is expected


async def test_role_cache_miss_fetches_before_declaring_deleted():
    role = FakeRole(2, 1)
    guild = SimpleNamespace(
        roles=[],
        fetch_roles=AsyncMock(return_value=[role]),
        me=SimpleNamespace(
            guild_permissions=SimpleNamespace(manage_roles=True),
            top_role=FakeRole(3, 10),
        ),
    )
    roles = await DiscordOnboarding(SimpleNamespace(get_guild=lambda _: guild)).roles(
        1, (2, 4)
    )
    assert [role.id for role in roles] == [2]
    guild.fetch_roles.assert_awaited_once()


async def test_channel_cache_miss_uses_api_and_permission_error_propagates():
    channel = Mock(spec=discord.TextChannel)
    channel.guild = SimpleNamespace(id=1)
    bot = SimpleNamespace(
        get_channel=lambda _: None, fetch_channel=AsyncMock(return_value=channel)
    )
    adapter = DiscordOnboarding(bot)
    assert await adapter.channel_exists(1, 2)
    bot.fetch_channel.side_effect = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "missing permission"
    )
    with pytest.raises(discord.Forbidden):
        await adapter.channel_exists(1, 2)
    bot.fetch_channel.side_effect = discord.NotFound(
        SimpleNamespace(status=404, reason="Not Found"), "deleted"
    )
    assert not await adapter.channel_exists(1, 2)


async def test_greeting_partial_update_and_length_limits():
    template = greeting_template(DEFAULT_GREETING, None, "custom", False)
    assert template.title == "Welcome!"
    assert template.description == "custom"
    assert not template.show_member_count
    with pytest.raises(OnboardingInputError):
        greeting_template(template, "x" * 156, None, True)
