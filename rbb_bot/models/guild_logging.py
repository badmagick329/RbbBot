from tortoise import fields
from tortoise.models import Model


class GuildLogging(Model):
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
