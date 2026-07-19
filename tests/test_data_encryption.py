import base64

import importlib.util
from pathlib import Path

import pytest
from tortoise import Tortoise
from rbb_bot.services.data_encryption_service import (
    DataEncryptionError,
    DataEncryptionService,
)


RELEASE_B_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "migrations"
    / "models"
    / "53_20260719_remove_legacy_plaintext_columns.py"
)


def load_release_b_migration():
    spec = importlib.util.spec_from_file_location(
        "remove_legacy_plaintext_columns", RELEASE_B_MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Release B encryption migration")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


async def add_release_a_plaintext_columns(connection):
    """Make the final-schema fixture look like the completed Release A schema."""
    await connection.execute_script(
        '''
        ALTER TABLE "guild" ADD COLUMN "prefix" VARCHAR(10);
        ALTER TABLE "guild" ADD COLUMN "emojis_channel_message" VARCHAR(2000);
        ALTER TABLE "greeting" ADD COLUMN "title" VARCHAR(256);
        ALTER TABLE "greeting" ADD COLUMN "description" VARCHAR(4096);
        ALTER TABLE "joinresponse" ADD COLUMN "content" VARCHAR(2000);
        ALTER TABLE "discorduser" ADD COLUMN "cached_username" VARCHAR(32);
        ALTER TABLE "discorduser" ADD COLUMN "blacklist" JSONB;
        ALTER TABLE "reminder" ADD COLUMN "text" VARCHAR(1500);
        ALTER TABLE "response" ADD COLUMN "content" VARCHAR(2000);
        ALTER TABLE "tag" ADD COLUMN "trigger" VARCHAR(200);
        ALTER TABLE "sourceentry" ADD COLUMN "emoji_string" VARCHAR(255);
        ALTER TABLE "sourceentry" ADD COLUMN "emoji_url" VARCHAR(255);
        ALTER TABLE "sourceentry" ADD COLUMN "source_url" VARCHAR(255);
        ALTER TABLE "sourceentry" ADD COLUMN "event" VARCHAR(255);
        ALTER TABLE "sourceentry" ADD COLUMN "jump_url" VARCHAR(255);
        ALTER TABLE "sourceentry" ADD COLUMN "conf_jump_url" VARCHAR(255);
        ALTER TABLE "botupdate" ADD COLUMN "message" TEXT;
        ALTER TABLE "botissue" ADD COLUMN "message" TEXT;
        '''
    )


def test_aes_gcm_ciphertexts_are_authenticated_and_randomised():
    key = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode()
    service = DataEncryptionService(key)

    first = service.encrypt("private value")
    second = service.encrypt("private value")

    assert first != second
    assert service.decrypt(first) == "private value"
    with pytest.raises(DataEncryptionError):
        service.decrypt(first[:-1] + ("A" if first[-1] != "A" else "B"))
    assert service.lookup_token("same value") == service.lookup_token("same value")
    assert service.lookup_token("same value") != service.lookup_token("other value")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_new_writes_store_ciphertext_and_preserve_model_behaviour(test_database):
    from rbb_bot.models import Guild, Response, Tag

    guild = await Guild.create(id=123, prefix="?")
    response = await Response.create(guild=guild, content="private response")
    tag = await Tag.create(guild=guild, trigger="private trigger")
    await tag.responses.add(response)

    connection = Tortoise.get_connection("default")
    _, rows = await connection.execute_query(
        'SELECT "prefix_ciphertext" FROM "guild" WHERE "id" = 123;'
    )
    assert "private" not in rows[0]["prefix_ciphertext"]
    _, rows = await connection.execute_query(
        'SELECT "content_ciphertext" FROM "response" WHERE "id" = $1;',
        [response.id],
    )
    assert "private response" not in rows[0]["content_ciphertext"]

    _, rows = await connection.execute_query(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'guild' AND column_name = 'prefix';
        """
    )
    assert rows == []

    loaded_tag = await Tag.by_id_or_trigger(guild, None, "private trigger")
    assert loaded_tag is not None
    assert loaded_tag.trigger == "private trigger"
    assert response.content == "private response"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_release_b_migration_rejects_unverified_plaintext(test_database):
    connection = Tortoise.get_connection("default")
    migration = load_release_b_migration()

    await add_release_a_plaintext_columns(connection)
    await connection.execute_script(
        """
        INSERT INTO "guild" ("id", "prefix") VALUES (456, '$');
        INSERT INTO "encryptionmetadata" ("id", "sentinel", "state", "format_version")
        VALUES (1, 'test', 'complete', 1);
        """
    )

    with pytest.raises(Exception, match="Encryption verification failed"):
        await connection.execute_script(await migration.upgrade(connection))


@pytest.mark.asyncio
@pytest.mark.integration
async def test_release_b_migration_removes_verified_plaintext(test_database):
    connection = Tortoise.get_connection("default")
    migration = load_release_b_migration()
    service = DataEncryptionService(
        base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode()
    )

    await add_release_a_plaintext_columns(connection)
    await connection.execute_query(
        """
        INSERT INTO "guild" ("id", "prefix", "prefix_ciphertext")
        VALUES ($1, $2, $3);
        """,
        [456, "$", service.encrypt("$")],
    )
    await connection.execute_query(
        """
        INSERT INTO "encryptionmetadata" ("id", "sentinel", "state", "format_version")
        VALUES (1, 'test', 'complete', 1);
        """
    )

    await connection.execute_script(await migration.upgrade(connection))

    _, rows = await connection.execute_query(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'guild' AND column_name = 'prefix';
        """
    )
    assert rows == []
