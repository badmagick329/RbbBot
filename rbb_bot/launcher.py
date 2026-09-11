import asyncio
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler

import aiohttp

from rbb_bot.rbb import RbbBot
from rbb_bot.settings.config import get_config, get_creds
from rbb_bot.settings.const import FilePaths

LOG_LEVEL = logging.INFO


async def run_until_stopped(bot, token):
    """Turn Docker's SIGTERM and console interrupts into awaited bot shutdown."""
    loop = asyncio.get_running_loop()
    stopping = asyncio.Event()
    previous = {
        sig: signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stopping.set))
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    client_task = asyncio.create_task(bot.start(token), name="discord-client")
    stop_task = asyncio.create_task(stopping.wait(), name="shutdown-signal")
    try:
        done, _ = await asyncio.wait(
            (client_task, stop_task), return_when=asyncio.FIRST_COMPLETED
        )
        if client_task in done:
            await client_task
    finally:
        try:
            # Stop setup_hook as well as an established gateway connection before
            # closing resources, so startup cannot create work during shutdown.
            client_task.cancel()
            stop_task.cancel()
            await asyncio.gather(client_task, stop_task, return_exceptions=True)
            await bot.close()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


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
    try:
        async with aiohttp.ClientSession() as web_client:
            async with RbbBot(config, creds, logger, web_client) as bot:
                await run_until_stopped(bot, creds.discord_token)
    finally:
        logger.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    asyncio.run(main())
