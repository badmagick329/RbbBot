import discord
from tortoise import fields
from tortoise.models import Model

from rbb_bot.settings.const import BOT_MAX_PREFIX
from rbb_bot.utils.mixins import ClientMixin


class CommandLog(Model, ClientMixin):
    id = fields.IntField(pk=True)
    command_name = fields.CharField(max_length=255)
    author_id = fields.BigIntField()
    guild_id = fields.BigIntField(null=True)
    channel_id = fields.BigIntField()
    message_id = fields.BigIntField()
    created_at = fields.DatetimeField(auto_now_add=True)
    prefix = fields.CharField(max_length=BOT_MAX_PREFIX)
    args = fields.JSONField(null=True)
    kwargs = fields.JSONField(null=True)

    async def get_author(self) -> discord.Member:
        self.client.get_guild(self.guild)

    @property
    def author(self) -> discord.User | int:
        user = self.client.get_user(self.author_id)
        return user if user else self.author_id

    @property
    def guild(self) -> discord.Guild | None:
        return self.client.get_guild(self.guild_id) if self.client else None

    @property
    def channel(self) -> discord.TextChannel | None:
        return self.client.get_channel(self.channel_id) if self.client else None

    async def get_message(self) -> discord.Message | None:
        return (
            await self.channel.fetch_message(self.message_id) if self.channel else None
        )

    class Meta:
        ordering = ["-created_at"]

    def __repr__(self):
        return (
            f"CommandLog<(id={self.id}, command_name={self.command_name}, "
            f"author_id={self.author_id}, guild_id={self.guild_id}, "
            f"channel_id={self.channel_id}, message_id={self.message_id}, "
            f"created_at={self.created_at}, prefix={self.prefix}, "
            f"args={self.args}, kwargs={self.kwargs})>"
        )

    def __str__(self):
        return self.__repr__()

    @classmethod
    async def get_logged_names(cls) -> list[str]:
        unique_names = list(
            set([i[0] for i in await cls.all().values_list("command_name")])
        )
        return sorted(unique_names)

    @classmethod
    async def get_command_count(cls, command_name: str) -> int:
        return await cls.filter(command_name=command_name).count()
