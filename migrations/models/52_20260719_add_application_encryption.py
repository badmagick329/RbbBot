from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "guild" ADD COLUMN "prefix_ciphertext" TEXT;
        ALTER TABLE "guild" ADD COLUMN "emojis_channel_message_ciphertext" TEXT;
        ALTER TABLE "greeting" ADD COLUMN "title_ciphertext" TEXT;
        ALTER TABLE "greeting" ADD COLUMN "description_ciphertext" TEXT;
        ALTER TABLE "joinresponse" ADD COLUMN "content_ciphertext" TEXT;
        ALTER TABLE "discorduser" ADD COLUMN "cached_username_ciphertext" TEXT;
        ALTER TABLE "discorduser" ADD COLUMN "blacklist_ciphertext" TEXT;
        ALTER TABLE "reminder" ADD COLUMN "text_ciphertext" TEXT;
        ALTER TABLE "response" ADD COLUMN "content_ciphertext" TEXT;
        ALTER TABLE "tag" ADD COLUMN "trigger_ciphertext" TEXT;
        ALTER TABLE "tag" ADD COLUMN "trigger_lookup" VARCHAR(64);
        ALTER TABLE "sourceentry" ADD COLUMN "emoji_string_ciphertext" TEXT;
        ALTER TABLE "sourceentry" ADD COLUMN "emoji_lookup" VARCHAR(64);
        ALTER TABLE "sourceentry" ADD COLUMN "emoji_url_ciphertext" TEXT;
        ALTER TABLE "sourceentry" ADD COLUMN "source_url_ciphertext" TEXT;
        ALTER TABLE "sourceentry" ADD COLUMN "event_ciphertext" TEXT;
        ALTER TABLE "sourceentry" ADD COLUMN "jump_url_ciphertext" TEXT;
        ALTER TABLE "sourceentry" ADD COLUMN "conf_jump_url_ciphertext" TEXT;
        ALTER TABLE "botupdate" ADD COLUMN "message_ciphertext" TEXT;
        ALTER TABLE "botissue" ADD COLUMN "message_ciphertext" TEXT;
        CREATE TABLE "encryptionmetadata" (
            "id" INT NOT NULL PRIMARY KEY,
            "sentinel" TEXT NOT NULL,
            "state" VARCHAR(20) NOT NULL,
            "format_version" INT NOT NULL DEFAULT 1
        );
        ALTER TABLE "tag" DROP CONSTRAINT IF EXISTS "uid_tag_trigger_0d3281";
        CREATE UNIQUE INDEX "uid_tag_guild_trigger_lookup" ON "tag" ("guild_id", "trigger_lookup");
        CREATE INDEX "idx_sourceentry_emoji_lookup" ON "sourceentry" ("emoji_lookup");
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_sourceentry_emoji_lookup";
        DROP INDEX IF EXISTS "uid_tag_guild_trigger_lookup";
        ALTER TABLE "tag" ADD CONSTRAINT "uid_tag_trigger_0d3281" UNIQUE ("trigger", "guild_id");
        DROP TABLE IF EXISTS "encryptionmetadata";
        ALTER TABLE "botissue" DROP COLUMN IF EXISTS "message_ciphertext";
        ALTER TABLE "botupdate" DROP COLUMN IF EXISTS "message_ciphertext";
        ALTER TABLE "sourceentry" DROP COLUMN IF EXISTS "conf_jump_url_ciphertext";
        ALTER TABLE "sourceentry" DROP COLUMN IF EXISTS "jump_url_ciphertext";
        ALTER TABLE "sourceentry" DROP COLUMN IF EXISTS "event_ciphertext";
        ALTER TABLE "sourceentry" DROP COLUMN IF EXISTS "source_url_ciphertext";
        ALTER TABLE "sourceentry" DROP COLUMN IF EXISTS "emoji_url_ciphertext";
        ALTER TABLE "sourceentry" DROP COLUMN IF EXISTS "emoji_lookup";
        ALTER TABLE "sourceentry" DROP COLUMN IF EXISTS "emoji_string_ciphertext";
        ALTER TABLE "tag" DROP COLUMN IF EXISTS "trigger_lookup";
        ALTER TABLE "tag" DROP COLUMN IF EXISTS "trigger_ciphertext";
        ALTER TABLE "response" DROP COLUMN IF EXISTS "content_ciphertext";
        ALTER TABLE "reminder" DROP COLUMN IF EXISTS "text_ciphertext";
        ALTER TABLE "discorduser" DROP COLUMN IF EXISTS "blacklist_ciphertext";
        ALTER TABLE "discorduser" DROP COLUMN IF EXISTS "cached_username_ciphertext";
        ALTER TABLE "joinresponse" DROP COLUMN IF EXISTS "content_ciphertext";
        ALTER TABLE "greeting" DROP COLUMN IF EXISTS "description_ciphertext";
        ALTER TABLE "greeting" DROP COLUMN IF EXISTS "title_ciphertext";
        ALTER TABLE "guild" DROP COLUMN IF EXISTS "emojis_channel_message_ciphertext";
        ALTER TABLE "guild" DROP COLUMN IF EXISTS "prefix_ciphertext";
    """
