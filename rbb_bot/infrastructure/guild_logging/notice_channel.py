import discord

from rbb_bot.application.guild_logging.report_notice import LogChannelUnavailable
from rbb_bot.views.guild_logging import guild_notice


class DiscordNoticeChannel:
    def __init__(self, bot):
        self.bot = bot

    async def post(self, channel_id, notice):
        try:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(channel_id)
            await channel.send(embed=guild_notice(notice))
        except (discord.Forbidden, discord.NotFound) as error:
            raise LogChannelUnavailable(channel_id) from error
