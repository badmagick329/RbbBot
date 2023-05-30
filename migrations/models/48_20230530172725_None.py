from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
CREATE TABLE IF NOT EXISTS "joinevent" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "_channel_id" BIGINT,
    "guild_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "joinresponse" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "content" VARCHAR(2000),
    "event_id" INT NOT NULL REFERENCES "joinevent" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "joinrole" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "role_id" BIGINT NOT NULL,
    "event_id" INT NOT NULL REFERENCES "joinevent" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "joinevent_joinrole" (
    "joinevent_id" INT NOT NULL REFERENCES "joinevent" ("id") ON DELETE CASCADE,
    "joinrole_id" INT NOT NULL REFERENCES "joinrole" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "joinevent_joinresponse" (
    "joinevent_id" INT NOT NULL REFERENCES "joinevent" ("id") ON DELETE CASCADE,
    "joinresponse_id" INT NOT NULL REFERENCES "joinresponse" ("id") ON DELETE CASCADE
);
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
