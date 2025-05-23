import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import aiohttp

from rbb_bot.rbb import RbbBot
from rbb_bot.settings.config import get_config, get_creds
from rbb_bot.settings.const import FilePaths

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))


LOG_LEVEL = logging.INFO


async def main():
    config = get_config()
    creds = get_creds()
    logger = logging.getLogger(__name__)
    logger.setLevel(LOG_LEVEL)
    if config.debug:
        handler = logging.StreamHandler(stream=sys.stdout)
    else:
        handler = RotatingFileHandler(
            filename=FilePaths.LOG_FILE,
            encoding="utf-8",
            mode="a",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler)
    async with aiohttp.ClientSession() as web_client:
        async with RbbBot(config, creds, logger, web_client) as bot:
            await bot.start(creds.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
