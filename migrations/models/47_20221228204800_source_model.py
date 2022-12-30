from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "sourceentry" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "emoji_string" VARCHAR(255) NOT NULL,
    "emoji_url" VARCHAR(255),
    "source_url" VARCHAR(255),
    "event" VARCHAR(255),
    "source_date" DATE,
    "guild_id" BIGINT,
    "channel_id" BIGINT NOT NULL,
    "message_id" BIGINT NOT NULL,
    "jump_url" VARCHAR(255) NOT NULL,
    "conf_message_id" BIGINT NOT NULL,
    "conf_jump_url" VARCHAR(255) NOT NULL,
    "user_id" INT NOT NULL REFERENCES "discorduser" ("_id") ON DELETE CASCADE
);;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "source";"""
