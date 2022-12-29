from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "discorduser" ADD "blacklist" JSONB;
        ALTER TABLE "discorduser" ADD "cached_username" VARCHAR(32);
        ALTER TABLE "discorduser" DROP COLUMN "weather_location";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "discorduser" ADD "weather_location" VARCHAR(100);
        ALTER TABLE "discorduser" DROP COLUMN "blacklist";
        ALTER TABLE "discorduser" DROP COLUMN "cached_username";"""
