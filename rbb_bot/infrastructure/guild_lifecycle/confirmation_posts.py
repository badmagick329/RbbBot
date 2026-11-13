from rbb_bot.infrastructure.sources.confirmation import SourceConfirmationService


class GuildConfirmationPosts:
    """Delete a departed guild's confirmation posts through the shared source service.

    The service is shared with privacy deletion; this adapter fixes the guild scope its
    failure log reports.
    """

    def __init__(self, service: SourceConfirmationService):
        self.service = service

    async def delete(self, guild_id: int, source_entries: list) -> bool:
        return await self.service.delete_confirmation_messages(
            source_entries, scope="guild", scope_id=guild_id
        )
