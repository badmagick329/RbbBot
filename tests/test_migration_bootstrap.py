import importlib.util
import json
import shutil
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

ENCRYPTION_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "models"
    / "52_20260719_add_application_encryption.py"
)


def load_encryption_migration():
    spec = importlib.util.spec_from_file_location(
        "add_application_encryption", ENCRYPTION_MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the application-encryption migration")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


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


async def add_legacy_discord_user_columns():
    connection = Tortoise.get_connection("default")
    await connection.execute_script(
        '''
        ALTER TABLE "discorduser" ADD COLUMN "cached_username" VARCHAR(32);
        ALTER TABLE "discorduser" ADD COLUMN "blacklist" JSONB;
        '''
    )


@pytest.mark.asyncio
async def test_bootstrap_records_legacy_migrations_without_running_them(test_database):
    await create_legacy_command_log_table()
    await add_legacy_discord_user_columns()

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
    await add_legacy_discord_user_columns()
    connection = Tortoise.get_connection("default")
    await connection.execute_script('DROP TABLE "sourceentry";')

    with pytest.raises(MigrationBootstrapError, match="sourceentry"):
        await baseline_existing_schema()


@pytest.mark.asyncio
async def test_baseline_makes_aerich_upgrade_apply_pending_migrations(
    test_database, tmp_path
):
    await create_legacy_command_log_table()
    connection = Tortoise.get_connection("default")
    await connection.execute_script('ALTER TABLE "guild" DROP COLUMN "departed_at";')
    await connection.execute_script(
        'ALTER TABLE "discorduser" DROP COLUMN "tag_opt_out";'
    )
    await add_legacy_discord_user_columns()
    # The current test schema represents Release B.  Recreate the one legacy
    # column needed by migration 52's historical downgrade before replaying
    # the pre-encryption migration sequence.
    await connection.execute_script(
        'ALTER TABLE "tag" ADD COLUMN "trigger" VARCHAR(200) NOT NULL DEFAULT \'\';'
    )
    encryption_migration = load_encryption_migration()
    await connection.execute_script(await encryption_migration.downgrade(connection))
    await baseline_existing_schema()
    await Tortoise.close_connections()

    # Release A must be deployed and its converter allowed to finish before
    # Release B can remove plaintext.  This baseline test intentionally
    # presents Aerich with migrations only through Release A.
    migration_root = tmp_path / "migrations"
    migration_models = migration_root / "models"
    migration_models.mkdir(parents=True)
    source_models = Path(__file__).parents[1] / "migrations" / "models"
    for migration_file in source_models.glob("*.py"):
        if migration_file.name.startswith("53_"):
            continue
        shutil.copy(migration_file, migration_models / migration_file.name)

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
        location=str(migration_root),
    )
    await command.init()

    assert await command.upgrade(run_in_transaction=True) == [
        "49_20260718_remove_command_log.py",
        "50_20260718_guild_lifecycle.py",
        "51_20260718_user_tag_opt_out.py",
        "52_20260719_add_application_encryption.py",
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
