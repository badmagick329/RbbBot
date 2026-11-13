from rbb_bot.application.custom_roles.contracts import CustomRoleSettings
from rbb_bot.domain.custom_roles import RoleOwnership
from rbb_bot.models import CustomRole, DiscordUser, Guild


class TortoiseCustomRoleRepository:
    """Keep the guild's custom-role settings and a durable allowlist of roles this feature
    created, scoped to their guild and owner."""

    async def settings(self, guild_id: int) -> CustomRoleSettings:
        # Reading must not create a configured guild; a missing row means the defaults.
        guild = await Guild.get_or_none(id=guild_id)
        if guild is None:
            return CustomRoleSettings()
        return CustomRoleSettings(guild.custom_roles_enabled, guild.max_custom_roles)

    async def set_enabled(self, guild_id: int, enabled: bool) -> None:
        await Guild.update_or_create(
            id=guild_id, defaults={"custom_roles_enabled": enabled}
        )

    async def set_max_roles(self, guild_id: int, max_roles: int) -> None:
        await Guild.update_or_create(
            id=guild_id, defaults={"max_custom_roles": max_roles}
        )

    async def record(self, guild_id: int, owner_id: int, role_id: int) -> None:
        guild = await Guild.get(id=guild_id)
        owner, _ = await DiscordUser.get_or_create(id=owner_id)
        await CustomRole.create(role_id=role_id, guild=guild, owner=owner)

    async def list(
        self, guild_id: int, owner_id: int | None = None
    ) -> tuple[RoleOwnership, ...]:
        query = CustomRole.filter(guild__id=guild_id)
        if owner_id is not None:
            query = query.filter(owner__id=owner_id)
        rows = await query.prefetch_related("owner")
        return tuple(RoleOwnership(row.role_id, row.owner.id) for row in rows)

    async def forget(self, guild_id: int, role_id: int) -> None:
        row = await CustomRole.filter(guild__id=guild_id, role_id=role_id).first()
        if row is not None:
            await row.delete()
