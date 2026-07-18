from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "discorduser" ADD "tag_opt_out" BOOL NOT NULL DEFAULT False;
        CREATE INDEX "idx_discorduser_tag_opt_242587" ON "discorduser" ("tag_opt_out");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_discorduser_tag_opt_242587";
        ALTER TABLE "discorduser" DROP COLUMN IF EXISTS "tag_opt_out";
    """
