"""Deletion of source-submission confirmation messages in Discord."""

import discord


class SourceConfirmationService:
    def __init__(self, bot):
        self.bot = bot

    async def delete_confirmation_messages(
        self, source_entries: list, *, scope: str, scope_id: int
    ) -> bool:
        """Delete every confirmation post, treating already-missing posts as deleted."""
        for source_entry in source_entries:
            try:
                channel = self.bot.get_channel(source_entry.conf_channel_id)
                if channel is None:
                    channel = await self.bot.fetch_channel(source_entry.conf_channel_id)
                message = await channel.fetch_message(source_entry.conf_message_id)
                await message.delete()
            except discord.NotFound:
                continue
            except (discord.Forbidden, discord.HTTPException):
                self.bot.logger.exception(
                    "Source confirmation deletion failed scope=%s scope_id=%s "
                    "source_entry_count=%s",
                    scope,
                    scope_id,
                    len(source_entries),
                )
                return False
        return True
