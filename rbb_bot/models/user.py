import discord
from tortoise import fields
from tortoise.models import Model

from rbb_bot.utils.mixins import ClientMixin


class DiscordUser(Model, ClientMixin):
    _id = fields.IntField(pk=True)
    id = fields.BigIntField(unique=True)
    cached_username = fields.CharField(max_length=32, null=True)
    blacklist = fields.JSONField(null=True)

    @property
    def user(self) -> discord.User | None:
        return self.client.get_user(self.id) if self.client else None

    def __repr__(self) -> str:
        return (
            f"<DiscordUser(_id={self._id},"
            f"id={self.id}, cached_username={self.cached_username}, "
            f"blacklist={self.blacklist})>"
        )

    def __str__(self) -> str:
        return self.__repr__()
