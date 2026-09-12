"""Only newly created custom roles acquire deletion authority; existing Discord roles cannot be safely inferred."""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE "customrole" (
            "role_id" BIGINT NOT NULL PRIMARY KEY,
            "guild_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE,
            "owner_id" INT NOT NULL REFERENCES "discorduser" ("_id") ON DELETE CASCADE
        );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return 'DROP TABLE "customrole";'
