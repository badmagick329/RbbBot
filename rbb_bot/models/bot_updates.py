from tortoise import fields
from tortoise.models import Model

from rbb_bot.models.encrypted import EncryptedModelMixin, EncryptedValue


class BotUpdate(EncryptedModelMixin, Model):
    id = fields.IntField(pk=True)
    message_ciphertext = fields.TextField(null=True)
    message = EncryptedValue("message_ciphertext")
    created_at = fields.DatetimeField(auto_now_add=True)

    def __repr__(self):
        return (
            f"BotUpdate<(id={self.id}, "
            f"message={self.message}, "
            f"created_at={self.created_at})>"
        )

    def __str__(self):
        return self.__repr__()


class BotIssue(EncryptedModelMixin, Model):
    id = fields.IntField(pk=True)
    message_ciphertext = fields.TextField(null=True)
    message = EncryptedValue("message_ciphertext")
    created_at = fields.DatetimeField(auto_now_add=True)

    def __repr__(self):
        return (
            f"BotIssue<(id={self.id}, "
            f"message={self.message}, "
            f"created_at={self.created_at})>"
        )

    def __str__(self):
        return self.__repr__()
