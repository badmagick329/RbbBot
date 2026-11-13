import discord

from rbb_bot.application.emotes.contracts import ChannelAccess, EmoteChannelUnavailable

# Discord JSON error code for "Unknown Channel".
UNKNOWN_CHANNEL = 10003


class DiscordEmotePoster:
    """One command's or event's view of a Discord guild for posting its emotes.

    Built per invocation around the `discord.Guild` that discord.py handed the command or
    event, whose emoji list stays current in the cache. It remembers each channel it
    resolved, so checking access and then posting fetches an uncached channel only once.

    Only `post` translates Discord errors: a channel that cannot be resolved while checking
    access surfaces as Discord's own error, as it did before this adapter existed.
    """

    def __init__(self, bot, guild: discord.Guild, emotes_per_message: int = 15):
        self.bot = bot
        self.guild = guild
        self.emotes_per_message = emotes_per_message
        self._channels = {}

    async def _channel(self, channel_id):
        channel = self._channels.get(channel_id) or self.bot.get_channel(channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(channel_id)
        self._channels[channel_id] = channel
        return channel

    async def access(self, channel_id):
        permissions = (await self._channel(channel_id)).permissions_for(self.guild.me)
        return ChannelAccess(
            manage_messages=permissions.manage_messages,
            read_message_history=permissions.read_message_history,
        )

    async def post(self, channel_id, message, delete_previous):
        try:
            channel = await self._channel(channel_id)
            await self._post(channel, message, delete_previous)
        except discord.Forbidden as error:
            raise EmoteChannelUnavailable(channel_id, deleted=False) from error
        except discord.NotFound as error:
            # A message deleted mid-purge also yields NotFound; only a missing
            # channel is the guild's to fix.
            if error.code != UNKNOWN_CHANNEL:
                raise
            raise EmoteChannelUnavailable(channel_id, deleted=True) from error

    async def _post(self, channel, message, delete_previous):
        if delete_previous:
            await channel.purge(limit=None)
            async for previous in channel.history(limit=100):
                await previous.delete()

        static = [e for e in self.guild.emojis if not e.animated]
        animated = [e for e in self.guild.emojis if e.animated]
        # Static and animated emotes never share a message.
        for emotes in (static, animated):
            for start in range(0, len(emotes), self.emotes_per_message):
                batch = emotes[start : start + self.emotes_per_message]
                await channel.send("".join(str(e) for e in batch))

        if message:
            await channel.send(message)
