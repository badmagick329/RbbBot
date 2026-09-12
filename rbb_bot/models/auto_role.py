from tortoise import fields
from tortoise.models import Model


class AutoRole(Model):
    _id = fields.IntField(pk=True)
    guild_id = fields.BigIntField()
    role_id = fields.BigIntField()

    class Meta:  # type: ignore
        unique_together = (("guild_id", "role_id"),)
