from dataclasses import dataclass

from rbb_bot.application.member_onboarding.contracts import (
    MemberInfo,
    OnboardingRepository,
    OnboardingDiscord,
)
from rbb_bot.domain.member_onboarding.configuration import OnboardingInputError


@dataclass(frozen=True)
class RoleAssignmentResult:
    applied_members: int
    failures: tuple[tuple[int, Exception], ...]
    skipped_role_ids: tuple[int, ...]


class ConfigureAutoRoles:
    def __init__(self, repository: OnboardingRepository, discord: OnboardingDiscord):
        self.repository = repository
        self.discord = discord

    async def available(self, guild_id: int):
        ids = await self.repository.role_ids(guild_id)
        roles = await self.discord.roles(guild_id, ids)
        found = {role.id for role in roles}
        # The adapter fetches missing roles before reporting them as deleted.
        deleted = tuple(role_id for role_id in ids if role_id not in found)
        if deleted:
            await self.repository.remove_roles(guild_id, deleted)
        return roles

    async def add(self, guild_id: int, role_id: int) -> bool:
        roles = await self.discord.roles(guild_id, (role_id,))
        if not roles or not roles[0].assignable:
            raise OnboardingInputError(
                "I cannot assign this role. Check Manage Roles permission, role hierarchy, and whether the role is managed."
            )
        await self.available(guild_id)
        return await self.repository.add_role(guild_id, role_id)

    async def remove(self, guild_id: int, ids: tuple[int, ...]) -> int:
        return await self.repository.remove_roles(guild_id, ids)

    async def clear(self, guild_id: int) -> int:
        return await self.repository.remove_roles(
            guild_id, await self.repository.role_ids(guild_id)
        )


class ApplyAutoRoles:
    """A deleted/unassignable role or one member's failure must not block the rest of a bulk assignment."""

    def __init__(self, configured: ConfigureAutoRoles, discord: OnboardingDiscord):
        self.configured = configured
        self.discord = discord

    async def execute(
        self, guild_id: int, members: tuple[MemberInfo, ...], include_bots: bool = False
    ) -> RoleAssignmentResult:
        roles = await self.configured.available(guild_id)
        assignable = tuple(role.id for role in roles if role.assignable)
        skipped = tuple(role.id for role in roles if not role.assignable)
        successes = 0
        failures = []
        for member in members:
            if member.bot and not include_bots:
                continue
            missing = tuple(
                role_id for role_id in assignable if role_id not in member.role_ids
            )
            if not missing:
                continue
            try:
                await self.discord.apply_roles(guild_id, member.id, missing)
                successes += 1
            except Exception as error:
                failures.append((member.id, error))
        return RoleAssignmentResult(successes, tuple(failures), skipped)
