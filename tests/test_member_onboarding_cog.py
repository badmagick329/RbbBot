from unittest.mock import Mock, patch

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
