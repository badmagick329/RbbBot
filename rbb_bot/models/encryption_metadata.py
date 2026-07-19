from tortoise import fields
from tortoise.models import Model


class EncryptionMetadata(Model):
    """Singleton state used to validate the configured encryption key at startup."""

    id = fields.IntField(pk=True)
    sentinel = fields.TextField()
    state = fields.CharField(max_length=20)
    format_version = fields.IntField(default=1)
