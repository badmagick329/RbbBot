from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "botissue" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "message" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);;
        CREATE TABLE IF NOT EXISTS "botupdate" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "message" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "botissue";
        DROP TABLE IF EXISTS "botupdate";"""
