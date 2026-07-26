import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "rbb_bot"))
from rbb_bot.cogs.kpop_cog import KpopCog
from rbb_bot.cogs.kpop_cog import Release as KpopRelease
from rbb_bot.models import Release
from rbb_bot.utils.scraper import Scraper


def test_scraper_uses_the_canonical_tortoise_release_model():
    assert KpopRelease is Release


@pytest.mark.asyncio
async def test_scheduled_scraper_failure_is_logged_and_does_not_escape():
    logger = Mock()
    cog = object.__new__(KpopCog)
    cog.bot = SimpleNamespace(logger=logger)
    cog.scraper = SimpleNamespace(scrape=AsyncMock(side_effect=RuntimeError("db down")))

    await KpopCog.update_comebacks_task.coro(cog)

    logger.exception.assert_called_once_with("Scheduled release scraper failed")


@pytest.mark.asyncio
async def test_scraper_logs_failure_before_first_source_log(monkeypatch):
    logger = Mock()
    scraper = object.__new__(Scraper)
    scraper.logger = logger
    scraper.updating = False

    async def fail_to_load_releases():
        raise RuntimeError("db down")

    monkeypatch.setattr(scraper, "cbs_from_db", fail_to_load_releases)

    await scraper.scrape(urls=["https://example.invalid/releases"])

    logger.exception.assert_called_once_with("Unable to load releases before scraping")
