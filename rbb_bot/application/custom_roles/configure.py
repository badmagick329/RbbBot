from rbb_bot.application.custom_roles.contracts import (
    CustomRoleRefused,
    CustomRoleRepository,
    Refusal,
)
from rbb_bot.domain.custom_roles import MAX_ROLES_LIMIT


class ConfigureCustomRoles:
    def __init__(self, repository: CustomRoleRepository):
        self.repository = repository

    async def enable(self, guild_id: int, enabled: bool) -> None:
        await self.repository.set_enabled(guild_id, enabled)

    async def set_max_roles(self, guild_id: int, max_roles: int) -> None:
        if not 1 <= max_roles <= MAX_ROLES_LIMIT:
            raise CustomRoleRefused(Refusal.INVALID_MAX)
        await self.repository.set_max_roles(guild_id, max_roles)
