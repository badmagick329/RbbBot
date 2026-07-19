from typing import Optional

from tortoise import fields
from tortoise.models import Model

from rbb_bot.models import Guild
from rbb_bot.models.encrypted import EncryptedModelMixin, EncryptedValue


class Response(EncryptedModelMixin, Model):
    id = fields.IntField(pk=True)
    content_ciphertext = fields.TextField(null=True)
    content = EncryptedValue("content_ciphertext")
    guild = fields.ForeignKeyField("models.Guild", related_name="responses")

    class Meta:  # type: ignore
        ordering = ["id"]

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return (
            f"Response({self.id}), " f"Content: {self.content}, " f"Guild: {self.guild}"
        )

    @staticmethod
    async def by_id_or_content(
        guild: Guild, response_id: Optional[int], content: Optional[str]
    ) -> Optional[list["Response"]]:
        if response_id:
            return await Response.filter(guild=guild, id=response_id)
        elif content:
            return [
                response
                for response in await Response.filter(guild=guild)
                if response.content == content
            ]


class Tag(EncryptedModelMixin, Model):
    MAX_TRIGGER = 200
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

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return (
            f"Tag({self.id}), "
            f"{self.trigger} "
            f"{'(Inline)' if self.inline else ''} "
            f"{f'({self.use_count} uses)' if self.use_count else ''}"
        )

    @staticmethod
    async def by_id_or_trigger(
        guild: Guild, tag_id: Optional[int], trigger: Optional[str]
    ) -> Optional["Tag"]:
        if tag_id:
            return await Tag.get_or_none(guild=guild, id=tag_id)
        elif trigger:
            from rbb_bot.services.data_encryption_service import (
                get_data_encryption_service,
            )

            return await Tag.get_or_none(
                guild=guild,
                trigger_lookup=get_data_encryption_service().lookup_token(
                    trigger.lower().strip()
                ),
            )
