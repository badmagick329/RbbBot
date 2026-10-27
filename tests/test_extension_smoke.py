import asyncio
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest
from discord.ext import commands
from rbb_bot.settings.config import get_config


@pytest.mark.integration
@pytest.mark.asyncio
async def test_every_enabled_extension_loads_reloads_and_unloads(test_database):
    # Extension loading swaps fresh cog modules into sys.modules and unloading
    # evicts them. Later tests hold classes from the original modules, and
    # mock.patch now resolves targets through sys.modules, so restore them.
    original_cog_modules = {
        name: module
        for name, module in sys.modules.items()
        if name.startswith("rbb_bot.cogs.")
    }
    try:
        await _load_reload_and_unload_every_extension()
    finally:
        for name in [n for n in sys.modules if n.startswith("rbb_bot.cogs.")]:
            del sys.modules[name]
        sys.modules.update(original_cog_modules)


async def _load_reload_and_unload_every_extension():
    async with commands.Bot(command_prefix=".", intents=discord.Intents.all()) as bot:
        bot.config = get_config()
        bot.creds = SimpleNamespace(search_key="unused")
        bot.web_client = Mock()
        bot.logger = logging.getLogger("extension-smoke")
        bot.logging_ready = asyncio.Event()
        bot.guild_prefixes = {}
        bot.send_error = AsyncMock()
        scraper = SimpleNamespace(
            scrape=AsyncMock(), reddit=SimpleNamespace(close=AsyncMock())
        )
        with patch(
            "rbb_bot.infrastructure.releases.scraper.Scraper", return_value=scraper
        ):
            modules = [
                "rbb_bot.cogs." + p.stem
                for p in (Path(__file__).parents[1] / "rbb_bot/cogs").glob("*.py")
                if not p.stem.startswith("_")
            ]
            for module in modules:
                await bot.load_extension(module)
            names = {command.qualified_name for command in bot.walk_commands()}
            assert {
                "logging setup",
                "emote post now",
                "hangman start",
                "meme tweet",
                "crop adjust",
                "autorole add",
            } <= names
            for module in modules:
                await bot.reload_extension(module)
            for module in reversed(modules):
                await bot.unload_extension(module)
            assert not bot.cogs
