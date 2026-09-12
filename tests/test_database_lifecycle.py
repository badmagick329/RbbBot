import json
from datetime import datetime, timezone

import pytest
from tortoise import Tortoise

from rbb_bot.infrastructure.database.lifecycle import (
    ASSETS,
    MIGRATIONS,
    DatabaseStateError,
    initialize_empty_database,
    validate_migration_history,
)
from rbb_bot.upgrade_database import upgrade
from rbb_bot.data_encryption_preflight import verify_existing_encryption_key
from rbb_bot.models import DiscordUser, Reminder
from tests._database import get_test_database_url

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def config():
    return {
        "connections": {"default": get_test_database_url()},
        "apps": {
            "models": {
                "models": ["rbb_bot.models", "aerich.models"],
                "default_connection": "default",
            }
        },
        "timezone": "UTC",
    }


async def empty_schema():
    await Tortoise.get_connection("default").execute_script(
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    )


async def test_fresh_initialization_then_normal_upgrade_is_repeatable(test_database):
    await empty_schema()
    await initialize_empty_database()
    await validate_migration_history()
    await verify_existing_encryption_key()
    await upgrade(config())
    await upgrade(config())
    await Tortoise.init(config=config())
    _, rows = await Tortoise.get_connection("default").execute_query(
        "SELECT version FROM aerich ORDER BY id"
    )
    assert [r["version"] for r in rows] == [
        p.name
        for p in sorted(
            (MIGRATIONS / "models").glob("*.py"),
            key=lambda p: int(p.name.split("_")[0]),
        )
    ]
    assert await Reminder.all() == []


async def test_initializer_refuses_existing_data_without_changes(test_database):
    user = await DiscordUser.create(id=123)
    with pytest.raises(DatabaseStateError, match="empty public schema"):
        await initialize_empty_database()
    assert await DiscordUser.filter(pk=user.pk).exists()


async def test_initializer_rolls_back_schema_if_encryption_setup_fails(
    test_database, monkeypatch
):
    await empty_schema()
    from rbb_bot.infrastructure.database import lifecycle

    class BrokenKey:
        def encrypt(self, value):
            raise RuntimeError("encryption failed")

    monkeypatch.setattr(lifecycle, "get_data_encryption_service", BrokenKey)
    with pytest.raises(RuntimeError, match="encryption failed"):
        await initialize_empty_database()
    _, rows = await Tortoise.get_connection("default").execute_query(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    )
    assert rows == []


async def test_upgrade_rejects_empty_database_without_creating_tables(test_database):
    await empty_schema()
    with pytest.raises(DatabaseStateError, match="history is missing"):
        await upgrade(config())
    await Tortoise.init(config=config())
    _, rows = await Tortoise.get_connection("default").execute_query(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"
    )
    assert rows == []


async def test_upgrade_rejects_history_gap(test_database):
    await empty_schema()
    await initialize_empty_database()
    await Tortoise.get_connection("default").execute_query(
        "DELETE FROM aerich WHERE id = (SELECT MIN(id) FROM aerich)"
    )
    with pytest.raises(DatabaseStateError, match="incomplete"):
        await upgrade(config())


async def test_upgrade_applies_pending_migration_53_and_preserves_encrypted_reminders(
    test_database,
):
    await empty_schema()
    await initialize_empty_database()
    user = await DiscordUser.create(id=42)
    reminder = await Reminder.create(
        discord_user=user, text="keep this", due_time=datetime.now(timezone.utc)
    )
    ciphertext = reminder.text_ciphertext
    connection = Tortoise.get_connection("default")
    # Reconstruct Release A: these plaintext columns were removed by migration 53.
    legacy = {
        "guild": ["prefix", "emojis_channel_message"],
        "greeting": ["title", "description"],
        "joinresponse": ["content"],
        "discorduser": ["cached_username", "blacklist"],
        "reminder": ["text"],
        "response": ["content"],
        "tag": ["trigger"],
        "sourceentry": [
            "emoji_string",
            "emoji_url",
            "source_url",
            "event",
            "jump_url",
            "conf_jump_url",
        ],
        "botupdate": ["message"],
        "botissue": ["message"],
    }
    for table, columns in legacy.items():
        for column in columns:
            await connection.execute_script(
                f'ALTER TABLE "{table}" ADD COLUMN "{column}" TEXT;'
            )
    await connection.execute_query("DELETE FROM aerich WHERE version LIKE '53_%'")
    await upgrade(config())
    await Tortoise.init(config=config())
    stored = await Reminder.get(id=reminder.id)
    assert stored.text == "keep this"
    assert stored.text_ciphertext == ciphertext
    _, columns = await Tortoise.get_connection("default").execute_query(
        "SELECT column_name FROM information_schema.columns WHERE table_name='reminder' AND column_name='text'"
    )
    assert columns == []
    await validate_migration_history()


async def test_provisioning_and_upgrade_module_entrypoints(test_database):
    import asyncio
    import os
    import sys

    await empty_schema()
    environment = dict(os.environ, DB_URL=get_test_database_url())
    for module in ("rbb_bot.initialize_database", "rbb_bot.upgrade_database"):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            module,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        assert process.returncode == 0, (stdout + stderr).decode()
    await validate_migration_history()
    await verify_existing_encryption_key()
