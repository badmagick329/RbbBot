from datetime import datetime, timezone

import discord
from discord import Embed, Forbidden, TextChannel
from discord.utils import format_dt
from tortoise import Model, fields

from rbb_bot.models import Guild
from rbb_bot.settings.const import DISCORD_MAX_MESSAGE, BotEmojis
from rbb_bot.utils.helpers import truncate
from rbb_bot.utils.mixins import ClientMixin


class Reminder(Model, ClientMixin):
    id = fields.IntField(pk=True)
    channel_id = fields.BigIntField(null=True)
    discord_user = fields.ForeignKeyField(
        "models.DiscordUser", related_name="reminders"
    )
    guild = fields.ForeignKeyField("models.Guild", related_name="reminders", null=True)
    text = fields.CharField(max_length=DISCORD_MAX_MESSAGE - 500, default="No Text")
    due_time = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)

    DEFAULT_TEXT = "No Text"
    MAX_TEXT = DISCORD_MAX_MESSAGE - 500

    def create_embed(self) -> Embed:
        embed = Embed(title="Reminder", color=0x00FF00)
        embed.add_field(name="Due", value=self.detailed_format(), inline=False)
        embed.add_field(
            name="Created at", value=format_dt(self.created_at, style="f"), inline=False
        )
        if self.channel:
            embed.add_field(
                name="Set by", value=self.discord_user.user.mention, inline=False
            )
        embed.set_thumbnail(url=BotEmojis.IRENE_TIME_URL)
        return embed

    @property
    def reminder_text(self) -> str:
        text = (
            f"{BotEmojis.IRENE_TIME} You told me to remind you: {self.text}"
            if self.text != Reminder.DEFAULT_TEXT
            else ""
        )
        text = f"{text}\nDue: {self.detailed_format()}\nCreated at {format_dt(self.created_at, style='f')}."
        if self.channel:
            text = f"{text}\nSet by {self.discord_user.user.mention}"
        return text

    @property
    def is_due(self) -> bool:
        return self.due_time <= datetime.utcnow().replace(tzinfo=timezone.utc)

    @property
    def channel(self) -> TextChannel | None:
        if self.channel_id and self.client:
            return self.client.get_channel(self.channel_id)

    def detailed_format(self, dt: datetime = None) -> str:
        if not dt:
            dt = self.due_time
        return f"{format_dt(dt, style='f')} ({format_dt(dt, style='R')})"

    def __repr__(self):
        return (
            f"{self.discord_user} - {self.text} | {self.due_time}. "
            f"Channel: {self.channel}. "
            f"Created at: {self.created_at}. "
            f"Is due: {self.is_due}. "
            f"Guild: {self.guild}. "
        )

    def __str__(self):
        channel_str = f"Channel: {self.channel.mention}. " if self.channel else ""
        return (
            f"{truncate(self.text, 50)}\nDue at {self.detailed_format()}. "
            f"{channel_str}"
            f"Created at {format_dt(self.created_at, style='f')}"
        )


class DiscordUser(Model, ClientMixin):
    _id = fields.IntField(pk=True)
    id = fields.BigIntField(unique=True)
    weather_location = fields.CharField(max_length=100, null=True)

    @property
    def user(self) -> discord.User | None:
        return self.client.get_user(self.id) if self.client else None

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.user} ({self.id})"
