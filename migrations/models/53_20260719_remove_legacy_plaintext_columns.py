"""Remove the plaintext columns after Release A has completed successfully.

This migration deliberately has no downgrade.  The encrypted recovery dump made
before Release B is the recovery route; recreating empty plaintext columns would
make an older application image appear to work while silently losing data.
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM "encryptionmetadata"
                WHERE "id" = 1 AND "state" = 'complete' AND "format_version" = 1
            ) THEN
                RAISE EXCEPTION 'Encryption conversion has not completed';
            END IF;

            IF EXISTS (
                SELECT 1 FROM "guild"
                WHERE ("prefix" IS NOT NULL AND "prefix_ciphertext" IS NULL)
                   OR ("emojis_channel_message" IS NOT NULL AND "emojis_channel_message_ciphertext" IS NULL)
            ) OR EXISTS (
                SELECT 1 FROM "greeting"
                WHERE ("title" IS NOT NULL AND "title_ciphertext" IS NULL)
                   OR ("description" IS NOT NULL AND "description_ciphertext" IS NULL)
            ) OR EXISTS (
                SELECT 1 FROM "joinresponse"
                WHERE "content" IS NOT NULL AND "content_ciphertext" IS NULL
            ) OR EXISTS (
                SELECT 1 FROM "discorduser"
                WHERE ("cached_username" IS NOT NULL AND "cached_username_ciphertext" IS NULL)
                   OR ("blacklist" IS NOT NULL AND "blacklist_ciphertext" IS NULL)
            ) OR EXISTS (
                SELECT 1 FROM "reminder"
                WHERE "text" IS NOT NULL AND "text_ciphertext" IS NULL
            ) OR EXISTS (
                SELECT 1 FROM "response"
                WHERE "content" IS NOT NULL AND "content_ciphertext" IS NULL
            ) OR EXISTS (
                SELECT 1 FROM "tag"
                WHERE ("trigger" IS NOT NULL AND "trigger_ciphertext" IS NULL)
                   OR ("trigger" IS NOT NULL AND "trigger_lookup" IS NULL)
            ) OR EXISTS (
                SELECT 1 FROM "sourceentry"
                WHERE ("emoji_string" IS NOT NULL AND "emoji_string_ciphertext" IS NULL)
                   OR ("emoji_string" IS NOT NULL AND "emoji_lookup" IS NULL)
                   OR ("emoji_url" IS NOT NULL AND "emoji_url_ciphertext" IS NULL)
                   OR ("source_url" IS NOT NULL AND "source_url_ciphertext" IS NULL)
                   OR ("event" IS NOT NULL AND "event_ciphertext" IS NULL)
                   OR ("jump_url" IS NOT NULL AND "jump_url_ciphertext" IS NULL)
                   OR ("conf_jump_url" IS NOT NULL AND "conf_jump_url_ciphertext" IS NULL)
            ) OR EXISTS (
                SELECT 1 FROM "botupdate"
                WHERE "message" IS NOT NULL AND "message_ciphertext" IS NULL
            ) OR EXISTS (
                SELECT 1 FROM "botissue"
                WHERE "message" IS NOT NULL AND "message_ciphertext" IS NULL
            ) THEN
                RAISE EXCEPTION 'Encryption verification failed: plaintext values remain without ciphertext';
            END IF;
        END $$;

        ALTER TABLE "guild" DROP COLUMN "prefix";
        ALTER TABLE "guild" DROP COLUMN "emojis_channel_message";
        ALTER TABLE "greeting" DROP COLUMN "title";
        ALTER TABLE "greeting" DROP COLUMN "description";
        ALTER TABLE "joinresponse" DROP COLUMN "content";
        ALTER TABLE "discorduser" DROP COLUMN "cached_username";
        ALTER TABLE "discorduser" DROP COLUMN "blacklist";
        ALTER TABLE "reminder" DROP COLUMN "text";
        ALTER TABLE "response" DROP COLUMN "content";
        ALTER TABLE "tag" DROP COLUMN "trigger";
        ALTER TABLE "sourceentry" DROP COLUMN "emoji_string";
        ALTER TABLE "sourceentry" DROP COLUMN "emoji_url";
        ALTER TABLE "sourceentry" DROP COLUMN "source_url";
        ALTER TABLE "sourceentry" DROP COLUMN "event";
        ALTER TABLE "sourceentry" DROP COLUMN "jump_url";
        ALTER TABLE "sourceentry" DROP COLUMN "conf_jump_url";
        ALTER TABLE "botupdate" DROP COLUMN "message";
        ALTER TABLE "botissue" DROP COLUMN "message";
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    raise RuntimeError(
        "Migration 53 is intentionally irreversible. Restore the encrypted recovery dump instead."
    )
