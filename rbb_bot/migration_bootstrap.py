"""One-time, guarded Aerich baseline for the pre-Aerich production schema."""

import asyncio
import json

from aerich.utils import get_models_describe
from tortoise import Tortoise
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction


BASELINE_VERSIONS = (
    "43_20221227113530_None.py",
    "44_20221227113844_command_log.py",
    "45_20221228171301_bot updates.py",
    "46_20221228201445_source_update.py",
    "47_20221228204800_source_model.py",
    "48_20230530172725_None.py",
)

EXPECTED_TABLES = {
    "aerich",
    "artist",
    "autorole",
    "botissue",
    "botupdate",
    "commandlog",
    "discorduser",
    "diskcache",
    "greeting",
    "guild",
    "guildlogging",
    "joinevent",
    "joinevent_joinresponse",
    "joinevent_joinrole",
    "joinresponse",
    "joinrole",
    "release",
    "releasetype",
    "reminder",
    "response",
    "sourceentry",
    "tag",
    "tag_response",
}

EXPECTED_DISCORD_USER_COLUMNS = {
    "_id",
    "id",
    "blacklist",
    "cached_username",
}


class MigrationBootstrapError(RuntimeError):
    """Raised when a database is not safe to mark as baselined."""


async def _get_table_names(connection: BaseDBAsyncClient) -> set[str]:
    _, rows = await connection.execute_query(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
    )
    return {row["tablename"] for row in rows}


async def _get_discord_user_columns(connection: BaseDBAsyncClient) -> set[str]:
    _, rows = await connection.execute_query(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'discorduser';
        """
    )
    return {row["column_name"] for row in rows}


async def _validate_legacy_schema(connection: BaseDBAsyncClient) -> None:
    missing_tables = EXPECTED_TABLES - await _get_table_names(connection)
    if missing_tables:
        raise MigrationBootstrapError(
            "Refusing to baseline: database is missing expected tables: "
            + ", ".join(sorted(missing_tables))
        )

    missing_columns = EXPECTED_DISCORD_USER_COLUMNS - await _get_discord_user_columns(
        connection
    )
    if missing_columns:
        raise MigrationBootstrapError(
            "Refusing to baseline: discorduser is missing expected columns: "
            + ", ".join(sorted(missing_columns))
        )


async def baseline_existing_schema() -> None:
    """Record migrations 43--48 without executing historical migration SQL."""
    async with in_transaction("default") as connection:
        await connection.execute_query("SELECT pg_advisory_xact_lock(691593824);")

        _, rows = await connection.execute_query(
            'SELECT COUNT(*) AS count FROM "aerich";'
        )
        if rows[0]["count"] != 0:
            raise MigrationBootstrapError(
                "Refusing to baseline: the aerich history table is not empty"
            )

        await _validate_legacy_schema(connection)
        model_snapshot = json.dumps(get_models_describe("models"))

        for version in BASELINE_VERSIONS:
            await connection.execute_query(
                """
                INSERT INTO "aerich" ("version", "app", "content")
                VALUES ($1, 'models', $2::jsonb);
                """,
                [version, model_snapshot],
            )


async def main() -> None:
    from rbb_bot.dbconfig import DB_CONFIG

    await Tortoise.init(config=DB_CONFIG)
    try:
        await baseline_existing_schema()
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
