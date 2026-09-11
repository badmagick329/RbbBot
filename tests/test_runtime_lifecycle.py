import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from rbb_bot import rbb
from rbb_bot.lib.discord_log_handler import DiscordLogHandler
from rbb_bot.cogs.kpop_cog import KpopCog
from rbb_bot.cogs.emojis_cog import EmojisCog

pytestmark = pytest.mark.asyncio


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setattr(
        rbb,
        "get_discord_settings",
        lambda: SimpleNamespace(owner_id=1, logger_channel_id=2),
    )
    return rbb.RbbBot(
        SimpleNamespace(default_prefix="."),
        SimpleNamespace(db_url="unused"),
        logging.Logger("lifecycle-test"),
        SimpleNamespace(close=AsyncMock()),
    )


async def test_shutdown_cancels_logging_before_ready_and_closes_database_once(
    bot, monkeypatch
):
    order = []
    bot.wait_until_ready = asyncio.Event().wait
    bot.logging_task = asyncio.create_task(bot.setup_logging())
    await asyncio.sleep(0)

    async def discord_close(self):
        assert bot.logging_task.cancelled()
        order.append("discord")

    async def database_close():
        order.append("database")

    monkeypatch.setattr(rbb.commands.Bot, "close", discord_close)
    monkeypatch.setattr(rbb.Tortoise, "close_connections", database_close)
    await asyncio.gather(bot.close(), bot.close())
    await bot.close()
    assert order == ["discord", "database"]
    assert bot.logger.handlers == []
    bot.web_client.close.assert_not_awaited()


async def test_logging_failure_is_observed_and_releases_waiters(bot, monkeypatch):
    bot.wait_until_ready = AsyncMock()
    handler = SimpleNamespace(
        setLevel=Mock(),
        setFormatter=Mock(),
        init=AsyncMock(side_effect=RuntimeError("no channel")),
        close=Mock(),
    )
    monkeypatch.setattr(rbb, "DiscordLogHandler", Mock(return_value=handler))
    recorder = Mock()
    bot.logger.addHandler(recorder)
    recorder.level = logging.ERROR
    await bot.setup_logging()
    assert bot.logging_ready.is_set()
    assert bot.logger.handlers == [recorder]
    handler.close.assert_called_once()
    assert recorder.handle.call_args.args[0].getMessage() == "Discord logging stopped"


async def test_active_log_handler_is_detached_on_cancellation(bot, monkeypatch):
    bot.wait_until_ready = AsyncMock()
    handler = DiscordLogHandler(bot, 2, 1, bot.logger)
    monkeypatch.setattr(handler, "init", AsyncMock())
    started = asyncio.Event()

    async def run():
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(handler, "run", run)
    monkeypatch.setattr(rbb, "DiscordLogHandler", Mock(return_value=handler))
    task = asyncio.create_task(bot.setup_logging())
    await started.wait()
    assert handler in bot.logger.handlers
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert handler not in bot.logger.handlers
    assert handler._closed


async def test_partial_startup_failure_still_releases_database(bot, monkeypatch):
    async def discord_close(self):
        raise RuntimeError("cleanup failed")

    close_database = AsyncMock()
    monkeypatch.setattr(rbb.commands.Bot, "close", discord_close)
    monkeypatch.setattr(rbb.Tortoise, "close_connections", close_database)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await bot.close()
    close_database.assert_awaited_once()


async def test_bot_setup_never_creates_schema(bot, monkeypatch):
    monkeypatch.setattr(rbb.Tortoise, "init", AsyncMock())
    generate = AsyncMock()
    monkeypatch.setattr(rbb.Tortoise, "generate_schemas", generate)
    monkeypatch.setattr(rbb.Guild, "all", AsyncMock(return_value=[]))
    bot.load_cogs = []
    bot.load_extension = AsyncMock()
    bot.wait_until_ready = asyncio.Event().wait
    await bot.setup_hook()
    generate.assert_not_awaited()
    bot.logging_task.cancel()
    await asyncio.gather(bot.logging_task, return_exceptions=True)
    rbb.ClientMixin.inject_client(None)


async def test_logging_enqueue_does_not_spawn_a_task(bot, monkeypatch):
    handler = DiscordLogHandler(bot, 2, 1, bot.logger)
    monkeypatch.setattr(
        asyncio,
        "create_task",
        lambda *a, **kw: pytest.fail("Logging must not spawn tasks"),
    )
    handler.emit(logging.LogRecord("test", logging.INFO, "", 1, "hello", (), None))
    assert handler.message_queue.get_nowait() == ("hello", logging.INFO)
    handler.close()


async def test_scraper_unload_waits_for_task_before_closing_reddit():
    cog = object.__new__(KpopCog)
    stopped = asyncio.Event()
    started = asyncio.Event()

    async def scrape():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    task = asyncio.create_task(scrape())
    await started.wait()

    async def close():
        assert stopped.is_set()

    cog.update_comebacks_task = SimpleNamespace(
        get_task=lambda: task, cancel=task.cancel
    )
    cog.scraper = SimpleNamespace(
        reddit=SimpleNamespace(close=AsyncMock(side_effect=close))
    )
    cog.bot = SimpleNamespace(logger=Mock())
    await cog.cog_unload()
    cog.scraper.reddit.close.assert_awaited_once()


async def test_emoji_unload_cancels_delayed_posts():
    cog = EmojisCog(SimpleNamespace(logger=Mock()))
    task = asyncio.create_task(asyncio.sleep(3600))
    cog.post_tasks.add(task)
    cog.post_datetimes[1] = object()
    task.add_done_callback(cog.post_finished)
    await cog.cog_unload()
    assert task.cancelled()
    assert not cog.post_tasks
    assert not cog.post_datetimes


async def test_sigterm_runs_awaited_shutdown_and_restores_handlers(monkeypatch):
    from rbb_bot import launcher

    registered = {}
    original = object()

    def install(sig, handler):
        old = registered.get(sig, original)
        registered[sig] = handler
        return old

    monkeypatch.setattr(launcher.signal, "signal", install)
    started = asyncio.Event()
    finished = asyncio.Event()

    async def start(token):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    bot = SimpleNamespace(start=start, close=AsyncMock())
    running = asyncio.create_task(launcher.run_until_stopped(bot, "token"))
    await started.wait()
    registered[launcher.signal.SIGTERM](launcher.signal.SIGTERM, None)
    await running
    bot.close.assert_awaited_once()
    assert finished.is_set()
    assert all(handler is original for handler in registered.values())


async def test_login_failure_propagates_after_cleanup(monkeypatch):
    from rbb_bot import launcher

    monkeypatch.setattr(launcher.signal, "signal", lambda *args: None)
    bot = SimpleNamespace(
        start=AsyncMock(side_effect=RuntimeError("login failed")), close=AsyncMock()
    )
    with pytest.raises(RuntimeError, match="login failed"):
        await launcher.run_until_stopped(bot, "token")
    bot.close.assert_awaited_once()
