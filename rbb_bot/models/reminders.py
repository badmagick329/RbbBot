from tortoise import fields
from tortoise.models import Model

from rbb_bot.models.encrypted import EncryptedModelMixin, EncryptedValue


class Reminder(EncryptedModelMixin, Model):
    id = fields.IntField(pk=True)
    channel_id = fields.BigIntField(null=True)
    discord_user = fields.ForeignKeyField(
        "models.DiscordUser", related_name="reminders"
    )
    guild = fields.ForeignKeyField("models.Guild", related_name="reminders", null=True)
    text_ciphertext = fields.TextField(null=True)
    text = EncryptedValue("text_ciphertext", default="No Text")
    due_time = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)
