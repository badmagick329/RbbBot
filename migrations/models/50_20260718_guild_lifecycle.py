from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "guild" ADD "departed_at" TIMESTAMPTZ;
        CREATE INDEX "idx_guild_departe_e6ad3c" ON "guild" ("departed_at");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_guild_departe_e6ad3c";
        ALTER TABLE "guild" DROP COLUMN IF EXISTS "departed_at";
    """
