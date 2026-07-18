import json
from pathlib import Path

import pytest
from aerich import Command
from tortoise import Tortoise

from rbb_bot.migration_bootstrap import (
    BASELINE_VERSIONS,
    MigrationBootstrapError,
    baseline_existing_schema,
)
from tests._database import get_test_database_url


pytestmark = pytest.mark.integration


async def create_legacy_command_log_table():
    connection = Tortoise.get_connection("default")
    await connection.execute_script(
        """
        CREATE TABLE "commandlog" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "command_name" VARCHAR(255) NOT NULL,
            "author_id" BIGINT NOT NULL,
            "guild_id" BIGINT,
            "channel_id" BIGINT NOT NULL,
            "message_id" BIGINT NOT NULL,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            "prefix" VARCHAR(10) NOT NULL,
            "args" JSONB,
            "kwargs" JSONB
        );
        """
    )


@pytest.mark.asyncio
async def test_bootstrap_records_legacy_migrations_without_running_them(test_database):
    await create_legacy_command_log_table()

    await baseline_existing_schema()

    connection = Tortoise.get_connection("default")
    _, rows = await connection.execute_query(
        'SELECT "version", "content" FROM "aerich" ORDER BY "id";'
    )
    assert [row["version"] for row in rows] == list(BASELINE_VERSIONS)
    assert "commandlog" not in json.dumps(rows[-1]["content"])

    with pytest.raises(MigrationBootstrapError, match="not empty"):
        await baseline_existing_schema()


@pytest.mark.asyncio
async def test_bootstrap_rejects_an_incomplete_schema(test_database):
    connection = Tortoise.get_connection("default")
    await connection.execute_script('DROP TABLE "sourceentry";')

    with pytest.raises(MigrationBootstrapError, match="sourceentry"):
        await baseline_existing_schema()


@pytest.mark.asyncio
async def test_baseline_makes_aerich_upgrade_apply_pending_migrations(
    test_database,
):
    await create_legacy_command_log_table()
    connection = Tortoise.get_connection("default")
    await connection.execute_script('ALTER TABLE "guild" DROP COLUMN "departed_at";')
    await connection.execute_script(
        'ALTER TABLE "discorduser" DROP COLUMN "tag_opt_out";'
    )
    await baseline_existing_schema()
    await Tortoise.close_connections()

    command = Command(
        tortoise_config={
            "connections": {"default": get_test_database_url()},
            "apps": {
                "models": {
                    "models": ["rbb_bot.models", "aerich.models"],
                    "default_connection": "default",
                }
            },
            "timezone": "UTC",
        },
        location=str(Path(__file__).parents[1] / "migrations"),
    )
    await command.init()

    assert await command.upgrade(run_in_transaction=True) == [
        "49_20260718_remove_command_log.py",
        "50_20260718_guild_lifecycle.py",
        "51_20260718_user_tag_opt_out.py",
    ]

    connection = Tortoise.get_connection("default")
    _, rows = await connection.execute_query(
        "SELECT to_regclass('public.commandlog') AS table_name;"
    )
    assert rows[0]["table_name"] is None
    _, rows = await connection.execute_query(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'guild'
          AND column_name = 'departed_at';
        """
    )
    assert [row["column_name"] for row in rows] == ["departed_at"]
    _, rows = await connection.execute_query(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'discorduser'
          AND column_name = 'tag_opt_out';
        """
    )
    assert [row["column_name"] for row in rows] == ["tag_opt_out"]
