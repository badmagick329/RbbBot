from tortoise.transactions import in_transaction

from rbb_bot.application.member_onboarding.contracts import (
    GreetingSettings,
    WelcomeSettings,
    WelcomeMessage,
)
from rbb_bot.domain.member_onboarding import GreetingTemplate
from rbb_bot.domain.member_onboarding.configuration import (
    DEFAULT_GREETING,
    greeting_template,
    check_role_capacity,
    OnboardingInputError,
)
from rbb_bot.models import Guild, Greeting, JoinEvent, JoinResponse, AutoRole


class TortoiseOnboardingRepository:
    """Preserve the encrypted columns and existing welcome-message links while serializing guild configuration edits."""

    @staticmethod
    async def _lock(guild_id, connection):
        await Guild.get_or_create(id=guild_id, using_db=connection)
        return (
            await Guild.filter(id=guild_id)
            .using_db(connection)
            .select_for_update()
            .get()
        )

    @staticmethod
    def _template(row):
        return GreetingTemplate(row.title, row.description, row.show_member_count)

    async def greeting(self, guild_id: int) -> GreetingSettings:
        guild = await Guild.get_or_none(id=guild_id)
        if guild is None:
            return GreetingSettings(None, None)
        row = await Greeting.get_or_none(guild=guild)
        return GreetingSettings(
            guild.greet_channel_id, self._template(row) if row else None
        )

    async def set_greeting_channel(self, guild_id: int, channel_id: int | None):
        async with in_transaction() as connection:
            guild = await self._lock(guild_id, connection)
            guild.greet_channel_id = channel_id
            await guild.save(using_db=connection, update_fields=["greet_channel_id"])

    async def update_greeting(
        self,
        guild_id: int,
        title: str | None,
        description: str | None,
        show_count: bool,
    ) -> GreetingSettings:
        async with in_transaction() as connection:
            guild = await self._lock(guild_id, connection)
            row = await Greeting.filter(guild=guild).using_db(connection).first()
            template = greeting_template(
                self._template(row) if row else DEFAULT_GREETING,
                title,
                description,
                show_count,
            )
            if row is None:
                row = await Greeting.create(guild=guild, using_db=connection)
            row.title, row.description, row.show_member_count = (
                template.title,
                template.description,
                template.show_member_count,
            )
            await row.save(
                using_db=connection,
                update_fields=[
                    "title_ciphertext",
                    "description_ciphertext",
                    "show_member_count",
                ],
            )
            return GreetingSettings(guild.greet_channel_id, template)

    async def welcome(self, guild_id: int) -> WelcomeSettings:
        event = await JoinEvent.filter(guild__id=guild_id).first()
        if event is None:
            return WelcomeSettings(None, ())
        responses = await event._responses.all().order_by("id")
        return WelcomeSettings(
            event._channel_id,
            tuple(WelcomeMessage(row.id, row.content) for row in responses),
        )

    async def set_welcome_channel(self, guild_id: int, channel_id: int | None):
        async with in_transaction() as connection:
            guild = await self._lock(guild_id, connection)
            event, _ = await JoinEvent.get_or_create(guild=guild, using_db=connection)
            event._channel_id = channel_id
            await event.save(using_db=connection, update_fields=["_channel_id"])

    async def add_messages(self, guild_id: int, messages: tuple[str, ...]) -> int:
        async with in_transaction() as connection:
            guild = await self._lock(guild_id, connection)
            event = await JoinEvent.filter(guild=guild).using_db(connection).first()
            if event is None or event._channel_id is None:
                raise OnboardingInputError("No channel assigned for welcome messages.")
            existing = {
                row.content
                for row in await JoinResponse.filter(event=event).using_db(connection)
            }
            added = 0
            for content in messages:
                if content in existing:
                    continue
                row = await JoinResponse.create(
                    event=event, content=content, using_db=connection
                )
                await event._responses.add(row, using_db=connection)
                existing.add(content)
                added += 1
            return added

    async def remove_messages(self, guild_id: int, ids: tuple[int, ...]) -> int:
        async with in_transaction() as connection:
            guild = (
                await Guild.filter(id=guild_id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if guild is None:
                return 0
            event = await JoinEvent.filter(guild=guild).using_db(connection).first()
            if event is None:
                return 0
            return (
                await JoinResponse.filter(event=event, id__in=ids)
                .using_db(connection)
                .delete()
            )

    async def role_ids(self, guild_id: int) -> tuple[int, ...]:
        return tuple(
            await AutoRole.filter(guild_id=guild_id)
            .order_by("_id")
            .values_list("role_id", flat=True)
        )

    async def add_role(self, guild_id: int, role_id: int) -> bool:
        async with in_transaction() as connection:
            await self._lock(guild_id, connection)
            ids = (
                await AutoRole.filter(guild_id=guild_id)
                .using_db(connection)
                .values_list("role_id", flat=True)
            )
            if role_id in ids:
                return False
            check_role_capacity(len(ids))
            await AutoRole.create(
                guild_id=guild_id, role_id=role_id, using_db=connection
            )
            return True

    async def remove_roles(self, guild_id: int, ids: tuple[int, ...]) -> int:
        return await AutoRole.filter(guild_id=guild_id, role_id__in=ids).delete()
