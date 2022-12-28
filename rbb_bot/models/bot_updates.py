from tortoise import fields
from tortoise.models import Model


class BotUpdate(Model):
    id = fields.IntField(pk=True)
    message = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    def __repr__(self):
        return (
            f"BotUpdate<(id={self.id}, "
            f"message={self.message}, "
            f"created_at={self.created_at})>"
        )

    def __str__(self):
        return self.__repr__()


class BotIssue(Model):
    id = fields.IntField(pk=True)
    message = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    def __repr__(self):
        return (
            f"BotIssue<(id={self.id}, "
            f"message={self.message}, "
            f"created_at={self.created_at})>"
        )

    def __str__(self):
        return self.__repr__()
