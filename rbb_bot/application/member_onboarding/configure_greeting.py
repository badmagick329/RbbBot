from dataclasses import dataclass
from rbb_bot.application.member_onboarding.contracts import (
    OnboardingRepository,
    OnboardingDiscord,
)
from rbb_bot.domain.member_onboarding.configuration import OnboardingInputError


@dataclass(frozen=True)
class UpdateGreeting:
    guild_id: int
    title: str | None = None
    description: str | None = None
    show_member_count: bool = True


class ConfigureGreeting:
    def __init__(self, repository: OnboardingRepository, discord: OnboardingDiscord):
        self.repository = repository
        self.discord = discord

    async def read(self, guild_id: int):
        return await self.repository.greeting(guild_id)

    async def set_channel(self, guild_id: int, channel_id: int | None):
        if channel_id is not None and not await self.discord.channel_exists(
            guild_id, channel_id
        ):
            raise OnboardingInputError("Channel no longer exists. Please reassign.")
        await self.repository.set_greeting_channel(guild_id, channel_id)

    async def execute(self, request: UpdateGreeting):
        return await self.repository.update_greeting(
            request.guild_id,
            request.title,
            request.description,
            request.show_member_count,
        )
