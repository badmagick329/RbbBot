from tortoise import fields
from tortoise.models import Model

from rbb_bot.models.encrypted import EncryptedModelMixin, EncryptedValue


class Response(EncryptedModelMixin, Model):
    id = fields.IntField(pk=True)
    content_ciphertext = fields.TextField(null=True)
    content = EncryptedValue("content_ciphertext")
    guild = fields.ForeignKeyField("models.Guild", related_name="responses")

    class Meta:  # type: ignore
        ordering = ["id"]


class Tag(EncryptedModelMixin, Model):
    id = fields.IntField(pk=True)
    trigger_ciphertext = fields.TextField(null=True)
    trigger_lookup = fields.CharField(max_length=64, null=True)
    trigger = EncryptedValue(
        "trigger_ciphertext",
        lookup_field="trigger_lookup",
        normalize_lookup=lambda value: str(value).lower().strip(),
    )
    inline = fields.BooleanField(default=False)
    guild = fields.ForeignKeyField("models.Guild", related_name="tags")
    responses = fields.ManyToManyField("models.Response", related_name="tags")
    created_at = fields.DatetimeField(auto_now_add=True)
    use_count = fields.IntField(default=0)

    class Meta:  # type: ignore
        unique_together = ["trigger_lookup", "guild"]
        ordering = ["id"]
