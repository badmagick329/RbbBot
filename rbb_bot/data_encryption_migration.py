"""Idempotently populate additive ciphertext columns before RBB starts."""

import asyncio

from tortoise import Tortoise
from tortoise.transactions import in_transaction

from rbb_bot.services.data_encryption_service import get_data_encryption_service


class DataEncryptionMigrationError(RuntimeError):
    pass


MODEL_NAMES = (
    "Guild",
    "Greeting",
    "JoinResponse",
    "DiscordUser",
    "Reminder",
    "Response",
    "Tag",
    "SourceEntry",
    "BotUpdate",
    "BotIssue",
)


async def _migrate_model(model, connection) -> None:
    for record in await model.all().using_db(connection):
        update_fields = []
        for public_name, spec in model._encrypted_field_specs.items():
            ciphertext = getattr(record, spec.ciphertext_field)
            legacy_value = (
                getattr(record, spec.legacy_field) if spec.legacy_field else None
            )

            if ciphertext is not None:
                # Authentication failures are fatal: silently accepting a wrong key
                # would make otherwise valid data appear corrupted.
                getattr(record, public_name)
            elif legacy_value is not None:
                setattr(record, public_name, legacy_value)
                update_fields.append(spec.ciphertext_field)

            if getattr(record, spec.ciphertext_field) is not None and spec.lookup_field:
                expected_token = get_data_encryption_service().lookup_token(
                    spec.normalize_lookup(getattr(record, public_name))
                )
                if getattr(record, spec.lookup_field) != expected_token:
                    setattr(record, spec.lookup_field, expected_token)
                    update_fields.append(spec.lookup_field)

        if update_fields:
            await record.save(
                update_fields=list(dict.fromkeys(update_fields)), using_db=connection
            )


async def _ensure_lookup_tokens(model, connection) -> None:
    for record in await model.all().using_db(connection):
        update_fields = []
        for public_name, spec in model._encrypted_field_specs.items():
            if not spec.lookup_field or getattr(record, spec.ciphertext_field) is None:
                continue
            expected_token = get_data_encryption_service().lookup_token(
                spec.normalize_lookup(getattr(record, public_name))
            )
            if getattr(record, spec.lookup_field) != expected_token:
                setattr(record, spec.lookup_field, expected_token)
                update_fields.append(spec.lookup_field)
        if update_fields:
            await record.save(update_fields=update_fields, using_db=connection)


async def verify_encryption_ready(connection) -> None:
    metadata = await (
        Tortoise.apps["models"]["EncryptionMetadata"]
        .filter(id=1)
        .using_db(connection)
        .first()
    )
    if metadata is None:
        raise DataEncryptionMigrationError("Encryption metadata is missing")
    if (
        get_data_encryption_service().decrypt(metadata.sentinel)
        != "rbb-encryption-sentinel-v1"
    ):
        raise DataEncryptionMigrationError(
            "Configured encryption key does not match database"
        )

    for model_name in MODEL_NAMES:
        model = Tortoise.apps["models"][model_name]
        for record in await model.all().using_db(connection):
            for public_name, spec in model._encrypted_field_specs.items():
                legacy_value = (
                    getattr(record, spec.legacy_field) if spec.legacy_field else None
                )
                ciphertext = getattr(record, spec.ciphertext_field)
                if legacy_value is not None and ciphertext is None:
                    raise DataEncryptionMigrationError(
                        f"{model_name} id={record.pk} field={public_name} has no ciphertext"
                    )
                if ciphertext is not None:
                    getattr(record, public_name)
                if (
                    spec.lookup_field
                    and ciphertext is not None
                    and getattr(record, spec.lookup_field) is None
                ):
                    raise DataEncryptionMigrationError(
                        f"{model_name} id={record.pk} field={public_name} has no lookup token"
                    )


async def migrate_encryption_data() -> None:
    async with in_transaction("default") as connection:
        await connection.execute_query("SELECT pg_advisory_xact_lock(691593825);")
        metadata_model = Tortoise.apps["models"]["EncryptionMetadata"]
        metadata = await metadata_model.filter(id=1).using_db(connection).first()
        service = get_data_encryption_service()
        if metadata is None:
            metadata = await metadata_model.create(
                id=1,
                sentinel=service.encrypt("rbb-encryption-sentinel-v1"),
                state="migrating",
            )
        elif service.decrypt(metadata.sentinel) != "rbb-encryption-sentinel-v1":
            raise DataEncryptionMigrationError(
                "Configured encryption key does not match database"
            )

        for model_name in MODEL_NAMES:
            await _migrate_model(Tortoise.apps["models"][model_name], connection)
        for model_name in MODEL_NAMES:
            await _ensure_lookup_tokens(Tortoise.apps["models"][model_name], connection)

        await verify_encryption_ready(connection)
        metadata.state = "complete"
        await metadata.save(update_fields=["state"], using_db=connection)


async def main() -> None:
    from rbb_bot.dbconfig import DB_CONFIG

    await Tortoise.init(config=DB_CONFIG)
    try:
        await migrate_encryption_data()
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
