-- Frozen schema through migration 53. Later changes belong in migrations/models.
CREATE TABLE "artist" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(510) NOT NULL
);
CREATE TABLE "autorole" (
    "_id" SERIAL NOT NULL PRIMARY KEY,
    "guild_id" BIGINT NOT NULL,
    "role_id" BIGINT NOT NULL,
    CONSTRAINT "uid_autorole_guild_i_7557dc" UNIQUE ("guild_id", "role_id")
);
CREATE TABLE "botissue" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "message_ciphertext" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE "botupdate" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "message_ciphertext" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE "discorduser" (
    "_id" SERIAL NOT NULL PRIMARY KEY,
    "id" BIGINT NOT NULL UNIQUE,
    "cached_username_ciphertext" TEXT,
    "blacklist_ciphertext" TEXT,
    "tag_opt_out" BOOL NOT NULL  DEFAULT False
);
CREATE INDEX "idx_discorduser_tag_opt_242587" ON "discorduser" ("tag_opt_out");
CREATE TABLE "diskcache" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "key" VARCHAR(510) NOT NULL,
    "value" JSONB,
    "accessed_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "uid_diskcache_key_4e2a80" UNIQUE ("key")
);
CREATE TABLE "encryptionmetadata" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "sentinel" TEXT NOT NULL,
    "state" VARCHAR(20) NOT NULL,
    "format_version" INT NOT NULL  DEFAULT 1
);
COMMENT ON TABLE "encryptionmetadata" IS 'Singleton state used to validate the configured encryption key at startup.';
CREATE TABLE "guild" (
    "_id" SERIAL NOT NULL PRIMARY KEY,
    "id" BIGINT NOT NULL UNIQUE,
    "prefix_ciphertext" TEXT,
    "emojis_channel_id" BIGINT,
    "greet_channel_id" BIGINT,
    "emojis_channel_message_ciphertext" TEXT,
    "delete_emoji_messages" BOOL NOT NULL  DEFAULT True,
    "custom_roles_enabled" BOOL NOT NULL  DEFAULT False,
    "max_custom_roles" INT NOT NULL  DEFAULT 2,
    "reminders_enabled" BOOL NOT NULL  DEFAULT False,
    "departed_at" TIMESTAMPTZ
);
CREATE INDEX "idx_guild_departe_e6ad3c" ON "guild" ("departed_at");
CREATE TABLE "greeting" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "title_ciphertext" TEXT,
    "description_ciphertext" TEXT,
    "show_member_count" BOOL NOT NULL  DEFAULT True,
    "guild_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE
);
CREATE TABLE "guildlogging" (
    "_id" SERIAL NOT NULL PRIMARY KEY,
    "channel_id" BIGINT  UNIQUE,
    "message_removed_enabled" BOOL NOT NULL  DEFAULT False,
    "message_edited_enabled" BOOL NOT NULL  DEFAULT False,
    "member_join_enabled" BOOL NOT NULL  DEFAULT False,
    "member_leave_enabled" BOOL NOT NULL  DEFAULT False,
    "guild_model_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE
);
CREATE INDEX "idx_guildloggin_guild_m_56539b" ON "guildlogging" ("guild_model_id");
CREATE TABLE "joinevent" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "_channel_id" BIGINT,
    "guild_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE
);
CREATE TABLE "joinresponse" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "content_ciphertext" TEXT,
    "event_id" INT NOT NULL REFERENCES "joinevent" ("id") ON DELETE CASCADE
);
CREATE TABLE "joinrole" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "role_id" BIGINT NOT NULL,
    "event_id" INT NOT NULL REFERENCES "joinevent" ("id") ON DELETE CASCADE
);
CREATE TABLE "releasetype" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL
);
CREATE TABLE "release" (
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
CREATE TABLE "reminder" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "channel_id" BIGINT,
    "text_ciphertext" TEXT,
    "due_time" TIMESTAMPTZ NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "discord_user_id" INT NOT NULL REFERENCES "discorduser" ("_id") ON DELETE CASCADE,
    "guild_id" INT REFERENCES "guild" ("_id") ON DELETE CASCADE
);
CREATE TABLE "response" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "content_ciphertext" TEXT,
    "guild_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE
);
CREATE TABLE "sourceentry" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "emoji_string_ciphertext" TEXT,
    "emoji_lookup" VARCHAR(64),
    "emoji_url_ciphertext" TEXT,
    "source_url_ciphertext" TEXT,
    "event_ciphertext" TEXT,
    "source_date" DATE,
    "guild_id" BIGINT,
    "channel_id" BIGINT NOT NULL,
    "message_id" BIGINT NOT NULL,
    "jump_url_ciphertext" TEXT,
    "conf_message_id" BIGINT NOT NULL,
    "conf_jump_url_ciphertext" TEXT,
    "user_id" INT NOT NULL REFERENCES "discorduser" ("_id") ON DELETE CASCADE
);
CREATE INDEX "idx_sourceentry_emoji_l_e8c151" ON "sourceentry" ("emoji_lookup");
CREATE TABLE "tag" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "trigger_ciphertext" TEXT,
    "trigger_lookup" VARCHAR(64),
    "inline" BOOL NOT NULL  DEFAULT False,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "use_count" INT NOT NULL  DEFAULT 0,
    "guild_id" INT NOT NULL REFERENCES "guild" ("_id") ON DELETE CASCADE,
    CONSTRAINT "uid_tag_trigger_2c15a0" UNIQUE ("trigger_lookup", "guild_id")
);
CREATE TABLE "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);
CREATE TABLE "joinevent_joinresponse" (
    "joinevent_id" INT NOT NULL REFERENCES "joinevent" ("id") ON DELETE CASCADE,
    "joinresponse_id" INT NOT NULL REFERENCES "joinresponse" ("id") ON DELETE CASCADE
);
CREATE TABLE "joinevent_joinrole" (
    "joinevent_id" INT NOT NULL REFERENCES "joinevent" ("id") ON DELETE CASCADE,
    "joinrole_id" INT NOT NULL REFERENCES "joinrole" ("id") ON DELETE CASCADE
);
CREATE TABLE "tag_response" (
    "tag_id" INT NOT NULL REFERENCES "tag" ("id") ON DELETE CASCADE,
    "response_id" INT NOT NULL REFERENCES "response" ("id") ON DELETE CASCADE
);
