import discord
from tortoise import fields
from tortoise.models import Model

from rbb_bot.utils.mixins import ClientMixin


class GuildLogging(Model, ClientMixin):
    _id = fields.IntField(pk=True)
    guild_model = fields.ForeignKeyField(
        "models.Guild",
        related_name="logging",  # reverse accessor: Guild.logging
        on_delete=fields.CASCADE,
        db_constraint=True,
        index=True,
    )

    channel_id = fields.BigIntField(unique=True, null=True)
    message_removed_enabled = fields.BooleanField(default=False)
    message_edited_enabled = fields.BooleanField(default=False)
    member_join_enabled = fields.BooleanField(default=False)
    member_leave_enabled = fields.BooleanField(default=False)

    @property
    def guild(self) -> discord.Guild | None:
        return self.client.get_guild(self.guild_model.id) if self.client else None

    @property
    def logging_channel(self) -> discord.TextChannel | None:
        if self.channel_id and self.client:
            return self.client.get_channel(self.channel_id)

    @property
    def channel_mention(self) -> str | None:
        logging_channel = self.logging_channel
        return None if logging_channel is None else logging_channel.mention

    async def disable(self):
        self.channel_id = None
        return await self.save()

    @property
    def is_disabled(self) -> bool:
        return self.channel_id is None

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return (
            f"GuildLogging<(guild_model_id={self.guild_model._id}, "
            f"channel_id={self.channel_id}, "
            f"message_removed_enabled={self.message_removed_enabled}, "
            f"message_edited_enabled={self.message_edited_enabled}, "
            f"member_join_enabled={self.member_join_enabled}, "
            f"member_leave_enabled={self.member_leave_enabled})>"
        )
