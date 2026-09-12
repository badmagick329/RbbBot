from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest
from discord.ext import commands

from rbb_bot.cogs.guild_cog import GuildCog
from rbb_bot.cogs.member_onboarding_cog import MemberOnboardingCog


def test_guild_and_onboarding_commands_have_separate_owners():
    guild_commands = {command.qualified_name for command in GuildCog.__cog_commands__}
    onboarding_commands = {
        command.qualified_name for command in MemberOnboardingCog.__cog_commands__
    }

    assert guild_commands == {"prefix", "say"}
    assert {"greet", "welcome", "autorole"} <= onboarding_commands
    assert not guild_commands & onboarding_commands


@pytest.mark.asyncio
async def test_member_onboarding_extension_loads_reloads_and_unloads():
    intents = discord.Intents.none()
    intents.guilds = True
    with patch("discord.voice_client.VoiceClient.warn_nacl", False):
        bot = commands.Bot(command_prefix="!", intents=intents)
    bot.logger = Mock()

    try:
        await bot.load_extension("rbb_bot.cogs.member_onboarding_cog")
        original_cog = bot.get_cog("MemberOnboardingCog")
        assert original_cog is not None
        assert original_cog.__module__ == "rbb_bot.cogs.member_onboarding_cog"

        await bot.reload_extension("rbb_bot.cogs.member_onboarding_cog")
        reloaded_cog = bot.get_cog("MemberOnboardingCog")
        assert reloaded_cog is not None
        assert reloaded_cog is not original_cog

        await bot.unload_extension("rbb_bot.cogs.member_onboarding_cog")
        assert bot.get_cog("MemberOnboardingCog") is None
        assert bot.get_command("welcome") is None
        assert bot.get_command("autorole") is None
    finally:
        await bot.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("can_send", [True, False])
@pytest.mark.parametrize("command", ["welcome_channel", "welcome_message"])
async def test_welcome_configuration_warns_when_delivery_is_unavailable(
    command, can_send
):
    cog = MemberOnboardingCog(Mock())
    cog.messages = SimpleNamespace(
        set_channel=AsyncMock(),
        add=AsyncMock(return_value=1),
        read=AsyncMock(return_value=SimpleNamespace(channel_id=12)),
    )
    cog.discord.can_send_messages = AsyncMock(return_value=can_send)
    ctx = SimpleNamespace(
        interaction=None, guild=SimpleNamespace(id=1), send=AsyncMock()
    )
    argument = (
        SimpleNamespace(id=12, mention="<#12>")
        if command == "welcome_channel"
        else "Welcome!"
    )
    await getattr(MemberOnboardingCog, command).callback(cog, ctx, argument)
    reply = ctx.send.call_args.args[0]
    assert ("don't have permissions" in reply) is not can_send
    cog.discord.can_send_messages.assert_awaited_once_with(1, 12)
    if command == "welcome_channel":
        cog.messages.set_channel.assert_awaited_once_with(1, 12)
    else:
        cog.messages.add.assert_awaited_once_with(1, ("Welcome!",))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view_channel,send_messages,expected",
    [(True, True, True), (True, False, False), (False, True, False)],
)
async def test_welcome_delivery_permissions_resolve_uncached_channel(
    view_channel, send_messages, expected
):
    from rbb_bot.infrastructure.member_onboarding.discord_actions import (
        DiscordOnboarding,
    )

    bot = Mock()
    bot.get_channel.return_value = None
    channel = Mock()
    channel.permissions_for.return_value = SimpleNamespace(
        view_channel=view_channel, send_messages=send_messages
    )
    bot.fetch_channel = AsyncMock(return_value=channel)
    assert await DiscordOnboarding(bot).can_send_messages(1, 12) is expected
    bot.fetch_channel.assert_awaited_once_with(12)
    channel.permissions_for.assert_called_once_with(bot.get_guild.return_value.me)


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["welcome_channel", "welcome_message"])
@pytest.mark.parametrize(
    "failure", ["forbidden", "not_found", "http", "network", "timeout"]
)
async def test_welcome_save_confirmation_survives_permission_lookup_failure(
    command, failure
):
    response = SimpleNamespace(status=403, reason="Unavailable")
    errors = {
        "forbidden": discord.Forbidden(response, "Missing Access"),
        "not_found": discord.NotFound(response, "Unknown Channel"),
        "http": discord.HTTPException(response, "Unavailable"),
        "network": OSError("Connection lost"),
        "timeout": TimeoutError(),
    }
    cog = MemberOnboardingCog(Mock())
    cog.messages = SimpleNamespace(
        set_channel=AsyncMock(),
        add=AsyncMock(return_value=1),
        read=AsyncMock(return_value=SimpleNamespace(channel_id=12)),
    )
    cog.discord.can_send_messages = AsyncMock(side_effect=errors[failure])
    ctx = SimpleNamespace(
        interaction=None, guild=SimpleNamespace(id=1), send=AsyncMock()
    )
    argument = (
        SimpleNamespace(id=12, mention="<#12>")
        if command == "welcome_channel"
        else "Welcome!"
    )
    await getattr(MemberOnboardingCog, command).callback(cog, ctx, argument)
    reply = ctx.send.call_args.args[0]
    assert reply.startswith(
        "Set the welcome channel" if command == "welcome_channel" else "Message added"
    )
    assert "couldn't verify delivery permissions" in reply
    if command == "welcome_channel":
        cog.messages.set_channel.assert_awaited_once_with(1, 12)
    else:
        cog.messages.add.assert_awaited_once_with(1, ("Welcome!",))


@pytest.mark.asyncio
async def test_message_save_confirmation_survives_concurrent_welcome_disable():
    cog = MemberOnboardingCog(Mock())
    cog.messages = SimpleNamespace(
        add=AsyncMock(return_value=1),
        read=AsyncMock(return_value=SimpleNamespace(channel_id=None)),
    )
    cog.discord.can_send_messages = AsyncMock()
    ctx = SimpleNamespace(
        interaction=None, guild=SimpleNamespace(id=1), send=AsyncMock()
    )
    await MemberOnboardingCog.welcome_message.callback(cog, ctx, "Welcome!")
    cog.messages.add.assert_awaited_once_with(1, ("Welcome!",))
    cog.discord.can_send_messages.assert_not_awaited()
    ctx.send.assert_awaited_once_with(
        "Message added\nWelcome delivery is currently disabled"
    )
