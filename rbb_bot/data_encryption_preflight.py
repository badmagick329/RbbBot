"""Verify the configured encryption key before destructive schema migrations."""

import asyncio

from tortoise import Tortoise

from rbb_bot.data_encryption_migration import verify_encryption_ready
from rbb_bot.services.data_encryption_service import get_data_encryption_service


class DataEncryptionPreflightError(RuntimeError):
    pass


async def verify_existing_encryption_key() -> None:
    """Validate the key and, when Release A exists, its database sentinel."""
    service = get_data_encryption_service()
    connection = Tortoise.get_connection("default")
    _, rows = await connection.execute_query(
        "SELECT to_regclass('public.encryptionmetadata') AS table_name;"
    )
    if rows[0]["table_name"] is None:
        return

    metadata = await Tortoise.apps["models"]["EncryptionMetadata"].get_or_none(id=1)
    if metadata is None:
        raise DataEncryptionPreflightError("Encryption metadata is missing")
    if service.decrypt(metadata.sentinel) != "rbb-encryption-sentinel-v1":
        raise DataEncryptionPreflightError(
            "Configured encryption key does not match database"
        )
    # Validate every existing ciphertext while the Release A plaintext columns
    # are still present.  Migration 53 separately verifies that each of those
    # plaintext values has a ciphertext counterpart before dropping them.
    await verify_encryption_ready(connection)


async def main() -> None:
    from rbb_bot.dbconfig import DB_CONFIG

    await Tortoise.init(config=DB_CONFIG)
    try:
        await verify_existing_encryption_key()
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
