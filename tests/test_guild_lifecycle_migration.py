import importlib.util
from pathlib import Path

import pytest
from tortoise import Tortoise


pytestmark = pytest.mark.integration

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "models"
    / "50_20260718_guild_lifecycle.py"
)


def load_guild_lifecycle_migration():
    spec = importlib.util.spec_from_file_location("guild_lifecycle", MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the guild lifecycle migration")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.mark.asyncio
async def test_guild_lifecycle_migration_adds_departure_state_and_index(test_database):
    connection = Tortoise.get_connection("default")
    await connection.execute_script(
        """
        DROP SCHEMA public CASCADE;
        CREATE SCHEMA public;
        CREATE TABLE "guild" (
            "_id" SERIAL NOT NULL PRIMARY KEY,
            "id" BIGINT NOT NULL UNIQUE,
            "prefix" VARCHAR(10) NOT NULL DEFAULT '!',
            "emojis_channel_id" BIGINT,
            "greet_channel_id" BIGINT,
            "emojis_channel_message" VARCHAR(2000),
            "delete_emoji_messages" BOOL NOT NULL DEFAULT True,
            "custom_roles_enabled" BOOL NOT NULL DEFAULT False,
            "max_custom_roles" INT NOT NULL DEFAULT 2,
            "reminders_enabled" BOOL NOT NULL DEFAULT False
        );
        """
    )
    migration = load_guild_lifecycle_migration()

    await connection.execute_script(await migration.upgrade(connection))

    _, columns = await connection.execute_query(
        """
        SELECT column_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'guild'
          AND column_name = 'departed_at';
        """
    )
    _, indexes = await connection.execute_query(
        """
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'guild'
          AND indexname = 'idx_guild_departe_e6ad3c';
        """
    )
    assert len(columns) == 1
    assert columns[0]["column_name"] == "departed_at"
    assert columns[0]["is_nullable"] == "YES"
    assert len(indexes) == 1
    assert indexes[0]["indexname"] == "idx_guild_departe_e6ad3c"

    await Tortoise.generate_schemas(safe=True)
    _, generated_indexes = await connection.execute_query(
        """
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'guild'
          AND indexdef LIKE '%(departed_at)%';
        """
    )
    assert [index["indexname"] for index in generated_indexes] == [
        "idx_guild_departe_e6ad3c"
    ]
