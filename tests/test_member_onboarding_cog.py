from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from rbb_bot.cogs.guild_cog import GuildCog, setup
from rbb_bot.presentation.discord import MemberOnboardingCog


def test_guild_and_onboarding_commands_have_separate_owners():
    guild_commands = {command.qualified_name for command in GuildCog.__cog_commands__}
    onboarding_commands = {
        command.qualified_name for command in MemberOnboardingCog.__cog_commands__
    }

    assert guild_commands == {"prefix", "say"}
    assert {"greet", "welcome", "autorole"} <= onboarding_commands
    assert not guild_commands & onboarding_commands


@pytest.mark.asyncio
async def test_guild_extension_registers_both_cogs():
    bot = SimpleNamespace(add_cog=AsyncMock(), logger=Mock())

    await setup(bot)

    registered_cogs = [call.args[0] for call in bot.add_cog.await_args_list]
    assert [type(cog) for cog in registered_cogs] == [GuildCog, MemberOnboardingCog]
