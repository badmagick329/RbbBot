"""Keep empty-database creation separate from upgrades of user data."""

import json
from pathlib import Path

from tortoise import Tortoise
from tortoise.transactions import in_transaction

from rbb_bot.infrastructure.encryption.codec import get_data_encryption_service

ASSETS = Path(__file__).parent
MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


class DatabaseStateError(RuntimeError):
    pass


async def initialize_empty_database() -> None:
    """Install the frozen baseline atomically; never infer an existing database's history."""
    history = json.loads((ASSETS / "initial_history.json").read_text())
    service = get_data_encryption_service()
    async with in_transaction("default") as connection:
        await connection.execute_query("SELECT pg_advisory_xact_lock(691593824)")
        _, objects = await connection.execute_query(
            "SELECT relname FROM pg_class WHERE relnamespace = 'public'::regnamespace"
        )
        if objects:
            raise DatabaseStateError(
                "Initialization requires an empty public schema; existing database was not changed"
            )
        await connection.execute_script((ASSETS / "initial_schema.sql").read_text())
        for version in history["versions"]:
            await connection.execute_query(
                "INSERT INTO aerich (version, app, content) VALUES ($1, $2, $3::jsonb)",
                [version, "models", json.dumps(history["content"])],
            )
        await connection.execute_query(
            "INSERT INTO encryptionmetadata (id, sentinel, state, format_version) VALUES (1, $1, $2, 1)",
            [service.encrypt("rbb-encryption-sentinel-v1"), "complete"],
        )


async def validate_migration_history() -> None:
    """Reject missing or divergent history instead of applying historical SQL by guesswork."""
    connection = Tortoise.get_connection("default")
    _, tables = await connection.execute_query(
        "SELECT to_regclass('public.aerich') AS name"
    )
    if tables[0]["name"] is None:
        raise DatabaseStateError(
            "Aerich history is missing. For an empty database run rbb_bot.initialize_database; "
            "existing databases need their migration history reconciled before startup."
        )
    _, rows = await connection.execute_query(
        "SELECT version FROM aerich WHERE app = 'models' ORDER BY id"
    )
    applied = [row["version"] for row in rows]
    versions = sorted(
        (p.name for p in (MIGRATIONS / "models").glob("*.py")),
        key=lambda name: int(name.split("_")[0]),
    )
    if not applied or applied != versions[: len(applied)]:
        raise DatabaseStateError(
            "Aerich history is empty, incomplete, or belongs to another release; database was not upgraded"
        )
