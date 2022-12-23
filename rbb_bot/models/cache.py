from tortoise import fields
from tortoise.models import Model


class DiskCache(Model):
    id = fields.IntField(pk=True)
    key = fields.CharField(max_length=510)
    value = fields.JSONField(null=True)
    accessed_at = fields.DatetimeField(auto_now_add=True)

    MAX_SIZE = 512

    class Meta: # type: ignore
        unique_together = ["key"]

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.key} - {self.value}"
