import discord

from rbb_bot.application.reminders.use_cases import ReminderData
from rbb_bot.views.reminders import reminder_message


class DiscordReminderDelivery:
    """Resolve uncached recipients and fall back to DMs when a channel is unavailable."""

    def __init__(self, bot):
        self.bot = bot

    async def send(self, reminder: ReminderData, *, late: bool) -> None:
        message = reminder_message(reminder, late=late)
        notice = ""
        if reminder.channel_id:
            if reminder.channel_enabled:
                try:
                    channel = self.bot.get_channel(reminder.channel_id)
                    if channel is None:
                        channel = await self.bot.fetch_channel(reminder.channel_id)
                    await channel.send(message)
                    return
                except (discord.Forbidden, discord.NotFound):
                    notice = "Could not send to the reminder channel. "
            else:
                notice = "The server has disabled channel reminders. "
        user = self.bot.get_user(reminder.user_id)
        if user is None:
            user = await self.bot.fetch_user(reminder.user_id)
        await user.send(notice + message)
