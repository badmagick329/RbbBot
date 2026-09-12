from rbb_bot.application.member_onboarding.contracts import (
    OnboardingRepository,
    OnboardingDiscord,
    WelcomeUrlSource,
)
from rbb_bot.domain.member_onboarding.configuration import (
    OnboardingInputError,
    welcome_message,
)


class ConfigureWelcomeMessages:
    """Allow removal while delivery is disabled and preserve channel assignments on reads."""

    def __init__(self, repository: OnboardingRepository, discord: OnboardingDiscord):
        self.repository = repository
        self.discord = discord

    async def read(self, guild_id: int):
        return await self.repository.welcome(guild_id)

    async def set_channel(self, guild_id: int, channel_id: int | None):
        if channel_id is not None and not await self.discord.channel_exists(
            guild_id, channel_id
        ):
            raise OnboardingInputError("Channel no longer exists. Please reassign.")
        await self.repository.set_welcome_channel(guild_id, channel_id)

    async def add(self, guild_id: int, messages: tuple[str, ...]) -> int:
        normalized = tuple(dict.fromkeys(welcome_message(value) for value in messages))
        settings = await self.read(guild_id)
        if settings.channel_id is None:
            raise OnboardingInputError("No channel assigned for welcome messages.")
        if not await self.discord.channel_exists(guild_id, settings.channel_id):
            raise OnboardingInputError(
                "Assigned channel no longer exists. Please reassign."
            )
        return await self.repository.add_messages(guild_id, normalized)

    async def remove(
        self, guild_id: int, message_id: int | None, content: str | None
    ) -> int:
        if message_id is None and content is None:
            raise OnboardingInputError("You must provide either an id or message")
        messages = (await self.read(guild_id)).messages
        ids = tuple(
            message.id
            for message in messages
            if (
                message.id == message_id
                if message_id is not None
                else message.content == content
            )
        )
        return await self.repository.remove_messages(guild_id, ids)

    async def clear(self, guild_id: int) -> int:
        settings = await self.read(guild_id)
        return await self.repository.remove_messages(
            guild_id, tuple(message.id for message in settings.messages)
        )


class ImportWelcomeUrls:
    """Validate the entire import before an atomic write, avoiding partially imported channel history."""

    def __init__(self, welcome: ConfigureWelcomeMessages, source: WelcomeUrlSource):
        self.welcome = welcome
        self.source = source

    async def execute(
        self, guild_id: int, channel_id: int, attachments: bool, remove: bool = False
    ) -> tuple[int, int]:
        urls = tuple(
            dict.fromkeys(await self.source.urls(guild_id, channel_id, attachments))
        )
        if remove:
            settings = await self.welcome.read(guild_id)
            ids = tuple(
                message.id for message in settings.messages if message.content in urls
            )
            count = await self.welcome.repository.remove_messages(guild_id, ids)
        else:
            count = await self.welcome.add(guild_id, urls)
        return count, len(urls)
