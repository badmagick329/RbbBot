from rbb_bot.application.emotes.contracts import EmoteChannelSettings
from rbb_bot.models import Guild


class TortoiseEmoteChannelRepository:
    """Keep a guild's emote-channel settings on its `Guild` row.

    Reads never create a row; every write does, since choosing a channel or message makes
    the guild a configured guild. Writes name their columns so a concurrent change to
    another feature's settings on the same row survives.
    """

    async def settings(self, guild_id: int) -> EmoteChannelSettings:
        guild = await Guild.get_or_none(id=guild_id)
        if guild is None:
            return EmoteChannelSettings()
        return EmoteChannelSettings(
            guild.emojis_channel_id,
            guild.emojis_channel_message,
            guild.delete_emoji_messages,
        )

    async def assign(self, guild_id: int, channel_id: int, delete_previous: bool):
        guild, _ = await Guild.get_or_create(id=guild_id)
        guild.emojis_channel_id = channel_id
        guild.delete_emoji_messages = delete_previous
        await guild.save(update_fields=["emojis_channel_id", "delete_emoji_messages"])

    async def unassign(self, guild_id: int):
        guild, _ = await Guild.get_or_create(id=guild_id)
        guild.emojis_channel_id = None
        await guild.save(update_fields=["emojis_channel_id"])

    async def set_message(self, guild_id: int, message: str | None):
        guild, _ = await Guild.get_or_create(id=guild_id)
        guild.emojis_channel_message = message
        await guild.save(update_fields=["emojis_channel_message_ciphertext"])
