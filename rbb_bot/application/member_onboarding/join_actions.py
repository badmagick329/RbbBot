from rbb_bot.domain.member_onboarding.configuration import OnboardingInputError
from rbb_bot.application.member_onboarding.contracts import (
    MemberInfo,
    OnboardingRepository,
    OnboardingDiscord,
)
from rbb_bot.application.member_onboarding.auto_roles import ApplyAutoRoles


class ConfiguredJoinActions:
    """Load each action independently so a broken greeting cannot suppress role assignment."""

    def __init__(
        self,
        guild_id: int,
        member: MemberInfo,
        repository: OnboardingRepository,
        discord: OnboardingDiscord,
        roles: ApplyAutoRoles,
        choose,
    ):
        self.guild_id, self.member = guild_id, member
        self.repository, self.discord, self.roles, self.choose = (
            repository,
            discord,
            roles,
            choose,
        )

    async def send_greeting(self):
        settings = await self.repository.greeting(self.guild_id)
        if settings.channel_id is not None and settings.template is not None:
            await self.discord.send_greeting(settings.channel_id, settings.template)

    async def send_join_response(self):
        settings = await self.repository.welcome(self.guild_id)
        if settings.channel_id is not None and settings.messages:
            await self.discord.send_welcome(
                settings.channel_id, self.choose(settings.messages).content
            )

    async def apply_auto_roles(self):
        result = await self.roles.execute(
            self.guild_id, (self.member,), include_bots=True
        )
        if result.failures:
            raise result.failures[0][1]
        if result.skipped_role_ids:
            raise OnboardingInputError(
                f"Unassignable auto roles: {result.skipped_role_ids}"
            )
