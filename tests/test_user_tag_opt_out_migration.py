import importlib.util
from pathlib import Path

import pytest
from tortoise import Tortoise


pytestmark = pytest.mark.integration

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "models"
    / "51_20260718_user_tag_opt_out.py"
)


def load_user_tag_opt_out_migration():
    spec = importlib.util.spec_from_file_location("user_tag_opt_out", MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the user tag opt-out migration")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


@pytest.mark.asyncio
async def test_user_tag_opt_out_migration_adds_default_and_index(test_database):
    connection = Tortoise.get_connection("default")
    await connection.execute_script(
        """
        ALTER TABLE "discorduser" DROP COLUMN "tag_opt_out";
        """
    )
    migration = load_user_tag_opt_out_migration()

    await connection.execute_script(await migration.upgrade(connection))
    await connection.execute_script(
        'INSERT INTO "discorduser" ("id", "cached_username") VALUES (123, \'test\');'
    )

    _, rows = await connection.execute_query(
        'SELECT "tag_opt_out" FROM "discorduser" WHERE "id" = 123;'
    )
    _, indexes = await connection.execute_query(
        """
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'discorduser'
          AND indexname = 'idx_discorduser_tag_opt_242587';
        """
    )
    assert rows[0]["tag_opt_out"] is False
    assert [index["indexname"] for index in indexes] == [
        "idx_discorduser_tag_opt_242587"
    ]

    await Tortoise.generate_schemas(safe=True)
    _, generated_indexes = await connection.execute_query(
        """
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'discorduser'
          AND indexdef LIKE '%(tag_opt_out)%';
        """
    )
    assert [index["indexname"] for index in generated_indexes] == [
        "idx_discorduser_tag_opt_242587"
    ]
