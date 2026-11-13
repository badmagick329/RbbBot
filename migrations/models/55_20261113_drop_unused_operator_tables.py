"""Drop operator tables that no code reads or writes, so they stop holding data nobody uses.

Aerich records the live model description when it applies a migration, so the
history row for this version no longer lists DiskCache, BotUpdate or BotIssue
and a later ``aerich migrate`` will not regenerate these drops. The downgrade
recreates the tables in their post-migration-53 shape, empty: their rows are
not recoverable from this migration.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE "diskcache";
        DROP TABLE "botupdate";
        DROP TABLE "botissue";
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE "botissue" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "message_ciphertext" TEXT,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE "botupdate" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "message_ciphertext" TEXT,
            "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE "diskcache" (
            "id" SERIAL NOT NULL PRIMARY KEY,
            "key" VARCHAR(510) NOT NULL,
            "value" JSONB,
            "accessed_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT "uid_diskcache_key_4e2a80" UNIQUE ("key")
        );
    """
