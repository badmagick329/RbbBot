import discord
from tortoise import fields
from tortoise.models import Model

from rbb_bot.utils.mixins import ClientMixin


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
