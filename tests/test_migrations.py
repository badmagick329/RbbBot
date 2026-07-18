import importlib.util
from pathlib import Path

import pytest
from tortoise import Tortoise


pytestmark = pytest.mark.integration

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "models"
    / "49_20260718_remove_command_log.py"
)


def load_remove_command_log_migration():
    spec = importlib.util.spec_from_file_location("remove_command_log", MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the command-log removal migration")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


async def command_log_table_exists() -> bool:
    connection = Tortoise.get_connection("default")
    _, rows = await connection.execute_query(
        "SELECT to_regclass('public.commandlog') AS table_name;"
    )
    return rows[0]["table_name"] is not None


@pytest.mark.asyncio
async def test_command_log_migration_drops_the_legacy_table(test_database):
    connection = Tortoise.get_connection("default")

    # The current model package must not recreate the removed table when its
    # schema is generated for a fresh database.
    assert not await command_log_table_exists()

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
    migration = load_remove_command_log_migration()

    assert await command_log_table_exists()

    await connection.execute_script(await migration.upgrade(connection))

    assert not await command_log_table_exists()

    # A release starts Tortoise after applying migrations; its current model
    # schema must initialise without bringing the deleted table back.
    await Tortoise.generate_schemas(safe=True)
    assert not await command_log_table_exists()


@pytest.mark.asyncio
async def test_command_log_migration_downgrade_only_recreates_an_empty_table(
    test_database,
):
    connection = Tortoise.get_connection("default")
    migration = load_remove_command_log_migration()

    await connection.execute_script(await migration.downgrade(connection))

    assert await command_log_table_exists()
    _, rows = await connection.execute_query("SELECT * FROM \"commandlog\";")
    assert rows == []
