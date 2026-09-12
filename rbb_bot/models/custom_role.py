from tortoise import fields
from tortoise.models import Model


class CustomRole(Model):
    """Deletion authority comes from recorded creation, never Discord member counts."""

    role_id = fields.BigIntField(pk=True, generated=False)
    guild = fields.ForeignKeyField(
        "models.Guild", related_name="custom_roles", on_delete=fields.CASCADE
    )
    owner = fields.ForeignKeyField(
        "models.DiscordUser", related_name="custom_roles", on_delete=fields.CASCADE
    )
