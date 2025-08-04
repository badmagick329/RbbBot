import discord
from tortoise import fields
from tortoise.models import Model

from rbb_bot.utils.mixins import ClientMixin


class AutoRole(Model, ClientMixin):
    _id = fields.IntField(pk=True)
    guild_id = fields.BigIntField()
    role_id = fields.BigIntField()

    class Meta:  # type: ignore
        unique_together = (("guild_id", "role_id"),)

    @property
    def guild(self) -> discord.Guild | None:
        return self.client.get_guild(self.guild_id) if self.client else None

    @property
    def role(self) -> discord.Role | None:
        if not self.client:
            return None

        guild = self.guild
        if not guild:
            return None

        return guild.get_role(self.role_id)

    def __str__(self) -> str:
        return f"<AutoRole(guild_id={self.guild_id}, role_id={self.role_id})>"

    def __repr__(self) -> str:
        return self.__str__()
