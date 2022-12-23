from tortoise import BaseDBAsyncClient  # type: ignore


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "artist" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(510) NOT NULL
);
CREATE TABLE IF NOT EXISTS "discorduser" (
    "_id" SERIAL NOT NULL PRIMARY KEY,
    "id" BIGINT NOT NULL UNIQUE,
    "weather_location" VARCHAR(100)
);
CREATE TABLE IF NOT EXISTS "diskcache" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "key" VARCHAR(510) NOT NULL,
    "value" JSONB,
    "accessed_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "uid_diskcache_key_4e2a80" UNIQUE ("key")
);
CREATE TABLE IF NOT EXISTS "guild" (
    "_id" SERIAL NOT NULL PRIMARY KEY,
    "id" BIGINT NOT NULL UNIQUE,
    "prefix" VARCHAR(10) NOT NULL  DEFAULT '?',
    "emojis_channel_id" BIGINT,
    "greet_channel_id" BIGINT,
    "emojis_channel_message" VARCHAR(2000),
    "delete_emoji_messages" BOOL NOT NULL  DEFAULT True,
    "custom_roles_enabled" BOOL NOT NULL  DEFAULT False,
    "max_custom_roles" INT NOT NULL  DEFAULT 2,
    "reminders_enabled" BOOL NOT NULL  DEFAULT False
);
CREATE TABLE IF NOT EXISTS "greeting" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "title" VARCHAR(255) NOT NULL  DEFAULT 'Welcome!',
    "description" VARCHAR(4096) NOT NULL  DEFAULT 'Welcome to the server!',
    "show_member_count" BOOL NOT NULL  DEFAULT True,
    "guild_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "releasetype" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL
);
CREATE TABLE IF NOT EXISTS "release" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "album_title" VARCHAR(510) NOT NULL,
    "title" VARCHAR(510) NOT NULL,
    "release_date" DATE NOT NULL,
    "release_time" TIMESTAMPTZ,
    "urls" JSONB,
    "reddit_urls" JSONB,
    "timezone" VARCHAR(30) NOT NULL  DEFAULT 'Asia/Seoul',
    "artist_id" INT NOT NULL REFERENCES "artist" ("id") ON DELETE CASCADE,
    "release_type_id" INT NOT NULL REFERENCES "releasetype" ("id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "reminder" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "channel_id" BIGINT,
    "text" VARCHAR(1500) NOT NULL  DEFAULT 'No Text',
    "due_time" TIMESTAMPTZ NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "discord_user_id" INT NOT NULL REFERENCES "discorduser" ("_id") ON DELETE CASCADE,
    "guild_id" INT REFERENCES "guild" ("_id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "response" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "content" VARCHAR(2000) NOT NULL,
    "guild_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "tag" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "trigger" VARCHAR(200) NOT NULL,
    "inline" BOOL NOT NULL  DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "use_count" INT NOT NULL  DEFAULT 0,
    "guild_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE,
    CONSTRAINT "uid_tag_trigger_0d3281" UNIQUE ("trigger", "guild_id")
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS "tag_response" (
    "tag_id" INT NOT NULL REFERENCES "tag" ("id") ON DELETE CASCADE,
    "response_id" INT NOT NULL REFERENCES "response" ("id") ON DELETE CASCADE
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
