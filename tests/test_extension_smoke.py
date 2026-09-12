import asyncio
import logging
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
