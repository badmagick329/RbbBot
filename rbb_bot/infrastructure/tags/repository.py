from tortoise.expressions import F
from tortoise.functions import Count
from tortoise.transactions import in_transaction

from rbb_bot.application.tags.contracts import AddTagResult, TagSelector
from rbb_bot.domain.tags.rules import (
    GuildTags,
    TagDefinition,
    TagResponse,
    TagInputError,
)
from rbb_bot.models import Guild, Response, Tag
from rbb_bot.infrastructure.encryption.codec import get_data_encryption_service


class TortoiseTagRepository:
    """Keep encrypted lookup and guild-scoped atomic edits behind the feature's repository."""

    @staticmethod
    def _data(tag) -> TagDefinition:
        return TagDefinition(
            tag.id,
            tag.trigger,
            tag.inline,
            tuple(TagResponse(r.id, r.content) for r in tag.responses),
            tag.use_count,
        )

    @staticmethod
    def _lookup(trigger: str) -> str:
        return get_data_encryption_service().lookup_token(trigger.lower().strip())

    async def guild_ids(self) -> list[int]:
        return await Guild.all().values_list("id", flat=True)

    async def snapshot(self, guild_id: int) -> GuildTags:
        guild = await Guild.get_or_none(id=guild_id)
        if guild is None:
            return GuildTags(None, ())
        tags = await Tag.filter(guild=guild).prefetch_related("responses")
        return GuildTags(
            guild.emojis_channel_id, tuple(self._data(tag) for tag in tags)
        )

    async def find_tag(self, selector: TagSelector) -> TagDefinition | None:
        query = Tag.filter(guild__id=selector.guild_id)
        if selector.tag_id is not None:
            query = query.filter(id=selector.tag_id)
        else:
            query = query.filter(trigger_lookup=self._lookup(selector.trigger))
        tag = await query.prefetch_related("responses").first()
        return self._data(tag) if tag else None

    async def responses(self, guild_id: int) -> list[TagResponse]:
        return [
            TagResponse(row.id, row.content)
            for row in await Response.filter(guild__id=guild_id)
        ]

    async def add(
        self, guild_id: int, trigger: str, response: str, inline: bool
    ) -> AddTagResult:
        async with in_transaction() as connection:
            guild, _ = await Guild.get_or_create(id=guild_id, using_db=connection)
            # Serialize edits to a guild, including concurrent creation of the same trigger.
            guild = (
                await Guild.filter(id=guild_id)
                .using_db(connection)
                .select_for_update()
                .get()
            )
            tag = (
                await Tag.filter(guild=guild, trigger_lookup=self._lookup(trigger))
                .using_db(connection)
                .first()
            )
            status = "updated"
            if tag is None:
                tag = await Tag.create(
                    guild=guild, trigger=trigger, inline=inline, using_db=connection
                )
                status = "created"
            existing = await tag.responses.all().using_db(connection)
            if any(item.content == response for item in existing):
                status = "duplicate"
            else:
                saved = await Response.create(
                    guild=guild, content=response, using_db=connection
                )
                await tag.responses.add(saved, using_db=connection)
            await tag.fetch_related("responses", using_db=connection)
            return AddTagResult(self._data(tag), status)

    async def rename(
        self, guild_id: int, tag_id: int, trigger: str
    ) -> TagDefinition | None:
        async with in_transaction() as connection:
            await Guild.filter(id=guild_id).using_db(
                connection
            ).select_for_update().first()
            tag = (
                await Tag.filter(guild__id=guild_id, id=tag_id)
                .using_db(connection)
                .first()
            )
            if tag is None:
                return None
            duplicate = (
                await Tag.filter(
                    guild__id=guild_id, trigger_lookup=self._lookup(trigger)
                )
                .exclude(id=tag_id)
                .using_db(connection)
                .exists()
            )
            if duplicate:
                raise TagInputError(f"Tag with trigger `{trigger}` already exists")
            tag.trigger = trigger
            await tag.save(
                using_db=connection,
                update_fields=["trigger_ciphertext", "trigger_lookup"],
            )
            await tag.fetch_related("responses", using_db=connection)
            return self._data(tag)

    async def remove_tag(self, guild_id: int, tag_id: int) -> bool:
        async with in_transaction() as connection:
            await Guild.filter(id=guild_id).using_db(
                connection
            ).select_for_update().first()
            tag = (
                await Tag.filter(guild__id=guild_id, id=tag_id)
                .using_db(connection)
                .first()
            )
            if tag is None:
                return False
            response_ids = (
                await tag.responses.all()
                .using_db(connection)
                .values_list("id", flat=True)
            )
            await tag.delete(using_db=connection)
            # A many-to-many response may still belong to another tag.
            orphans = (
                await Response.filter(guild_id=tag.guild_id, id__in=response_ids)
                .annotate(tag_count=Count("tags"))
                .filter(tag_count=0)
                .using_db(connection)
            )
            await Response.filter(
                id__in=[response.id for response in orphans]
            ).using_db(connection).delete()
            return True

    async def remove_responses(
        self, guild_id: int, response_ids: tuple[int, ...]
    ) -> int:
        async with in_transaction() as connection:
            guild = (
                await Guild.filter(id=guild_id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if guild is None:
                return 0
            deleted = (
                await Response.filter(guild=guild, id__in=response_ids)
                .using_db(connection)
                .delete()
            )
            if not deleted:
                return 0
            empty_tags = (
                await Tag.filter(guild=guild)
                .annotate(response_count=Count("responses"))
                .filter(response_count=0)
                .using_db(connection)
            )
            await Tag.filter(id__in=[tag.id for tag in empty_tags]).using_db(
                connection
            ).delete()
            return deleted

    async def record_use(self, tag_id: int) -> None:
        await Tag.filter(id=tag_id).update(use_count=F("use_count") + 1)
