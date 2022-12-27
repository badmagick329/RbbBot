from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "commandlog" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "command_name" VARCHAR(255) NOT NULL,
    "author_id" BIGINT NOT NULL,
    "guild_id" BIGINT,
    "channel_id" BIGINT NOT NULL,
    "message_id" BIGINT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "prefix" VARCHAR(10) NOT NULL,
    "args" JSONB,
    "kwargs" JSONB
);;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "commandlog";"""
