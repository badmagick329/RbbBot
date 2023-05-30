from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "discorduser" ADD IF NOT EXISTS "blacklist" JSONB;
        ALTER TABLE "discorduser" ADD IF NOT EXISTS "cached_username" VARCHAR(32);
        ALTER TABLE "discorduser" DROP COLUMN IF EXISTS "weather_location";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "discorduser" ADD IF NOT EXISTS "weather_location" VARCHAR(100);
        ALTER TABLE "discorduser" DROP COLUMN IF EXISTS "blacklist";
        ALTER TABLE "discorduser" DROP COLUMN IF EXISTS "cached_username";"""
