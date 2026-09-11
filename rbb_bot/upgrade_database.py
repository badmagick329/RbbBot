"""Shared upgrade entry point for development and production."""

import asyncio

from aerich import Command
from tortoise import Tortoise

from rbb_bot.data_encryption_preflight import verify_existing_encryption_key
from rbb_bot.data_encryption_migration import migrate_encryption_data
from rbb_bot.infrastructure.database.lifecycle import (
    MIGRATIONS,
    validate_migration_history,
)


async def upgrade(config: dict) -> None:
    command = Command(tortoise_config=config, app="models", location=str(MIGRATIONS))
    try:
        await command.init()
        await validate_migration_history()
        await verify_existing_encryption_key()
        await command.upgrade(run_in_transaction=True)
        await migrate_encryption_data()
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    from rbb_bot.dbconfig import DB_CONFIG

    asyncio.run(upgrade(DB_CONFIG))
