from typing import Optional

from tortoise import fields
from tortoise.models import Model

from rbb_bot.models import Guild
from rbb_bot.settings.const import DISCORD_MAX_MESSAGE


class Response(Model):
    id = fields.IntField(pk=True)
    content = fields.CharField(max_length=DISCORD_MAX_MESSAGE)
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
            return await Response.filter(guild=guild, content=content)


class Tag(Model):
    MAX_TRIGGER = 200
    id = fields.IntField(pk=True)
    trigger = fields.CharField(max_length=MAX_TRIGGER)
    inline = fields.BooleanField(default=False)
    guild = fields.ForeignKeyField("models.Guild", related_name="tags")
    responses = fields.ManyToManyField("models.Response", related_name="tags")
    created_at = fields.DatetimeField(auto_now_add=True)
    use_count = fields.IntField(default=0)

    class Meta:  # type: ignore
        unique_together = ["trigger", "guild"]
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
            return await Tag.get_or_none(guild=guild, trigger=trigger)
