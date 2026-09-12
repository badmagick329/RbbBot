from tortoise.transactions import in_transaction
from rbb_bot.models import Guild, GuildLogging
from rbb_bot.application.guild_logging.configure import LoggingSettings


class TortoiseLoggingRepository:
    @staticmethod
    def settings(row):
        return LoggingSettings(
            row.channel_id,
            row.member_join_enabled,
            row.member_leave_enabled,
            row.message_removed_enabled,
            row.message_edited_enabled,
        )

    async def read(self, guild_id):
        row = await GuildLogging.filter(guild_model__id=guild_id).first()
        return self.settings(row) if row else LoggingSettings()

    async def update(self, guild_id, changes):
        # Serialize creation and partial updates without adding schema constraints to old databases.
        async with in_transaction() as connection:
            await Guild.get_or_create(id=guild_id, using_db=connection)
            guild = (
                await Guild.filter(id=guild_id)
                .using_db(connection)
                .select_for_update()
                .get()
            )
            row, _ = await GuildLogging.get_or_create(
                guild_model=guild, using_db=connection
            )
            for field, value in changes.items():
                setattr(row, field, value)
            await row.save(using_db=connection, update_fields=list(changes))
            return self.settings(row)
