import discord
from discord.utils import format_dt

from rbb_bot.application.reminders.use_cases import DEFAULT_TEXT, ReminderData
from rbb_bot.settings.const import BotEmojis
from rbb_bot.utils.helpers import truncate
from rbb_bot.utils.views import ListView


def detailed_time(value):
    return f"{format_dt(value, style='f')} ({format_dt(value, style='R')})"


def reminder_summary(reminder: ReminderData) -> str:
    channel = f"\nChannel: <#{reminder.channel_id}>" if reminder.channel_id else ""
    return f"{truncate(reminder.text, 50)}\nDue: {detailed_time(reminder.due_time)}{channel}"


def reminder_message(reminder: ReminderData, *, late: bool) -> str:
    text = "Sorry for the late reminder. " if late else ""
    if reminder.text != DEFAULT_TEXT:
        text += f"{BotEmojis.IRENE_TIME} You told me to remind you: {reminder.text}"
    text += f"\nDue: {detailed_time(reminder.due_time)}\nCreated at {format_dt(reminder.created_at, style='f')}."
    if reminder.channel_id:
        text += f"\nSet by <@{reminder.user_id}>"
    return text


class RemindersList(ListView):
    def create_embed(self, reminders: list[ReminderData]) -> discord.Embed:
        user = self.ctx.author
        embed = discord.Embed(
            title=f"{user}'s reminders", color=discord.Color.blurple()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        for reminder in reminders:
            embed.add_field(
                name=f"[{reminder.id}] {truncate(reminder.text, 50)}",
                value=f"Created at {format_dt(reminder.created_at, style='f')}",
                inline=False,
            )
            channel = (
                f"Sending in <#{reminder.channel_id}>" if reminder.channel_id else ""
            )
            embed.add_field(
                name="Due", value=f"{detailed_time(reminder.due_time)} {channel}"
            )
        return embed
