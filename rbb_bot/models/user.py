import discord
from tortoise import fields
from tortoise.models import Model

from rbb_bot.models.encrypted import (
    EncryptedModelMixin,
    EncryptedValue,
    decode_json,
    encode_json,
)
from rbb_bot.utils.mixins import ClientMixin


class DiscordUser(EncryptedModelMixin, Model, ClientMixin):
    _id = fields.IntField(pk=True)
    id = fields.BigIntField(unique=True)
    cached_username_ciphertext = fields.TextField(null=True)
    cached_username = EncryptedValue("cached_username_ciphertext")
    blacklist_ciphertext = fields.TextField(null=True)
    blacklist = EncryptedValue(
        "blacklist_ciphertext",
        encode=encode_json,
        decode=decode_json,
    )
    tag_opt_out = fields.BooleanField(default=False, index=True)

    @property
    def user(self) -> discord.User | None:
        return self.client.get_user(self.id) if self.client else None

    def __repr__(self) -> str:
        return (
            f"<DiscordUser(_id={self._id},"
            f"id={self.id}, cached_username={self.cached_username}, "
            f"blacklist={self.blacklist}, tag_opt_out={self.tag_opt_out})>"
        )

    def __str__(self) -> str:
        return self.__repr__()
