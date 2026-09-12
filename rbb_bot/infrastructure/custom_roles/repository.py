from rbb_bot.domain.custom_roles import RoleOwnership
from rbb_bot.models import CustomRole, DiscordUser, Guild


class CustomRoleRepository:
    """Keep a durable allowlist of roles created by this feature, scoped to their guild and owner."""

    async def record(self, guild_id, owner_id, role_id):
        guild = await Guild.get(id=guild_id)
        owner, _ = await DiscordUser.get_or_create(id=owner_id)
        await CustomRole.create(role_id=role_id, guild=guild, owner=owner)

    async def list(self, guild_id, owner_id=None):
        query = CustomRole.filter(guild__id=guild_id)
        if owner_id is not None:
            query = query.filter(owner__id=owner_id)
        rows = await query.prefetch_related("owner")
        return tuple(RoleOwnership(row.role_id, row.owner.id) for row in rows)

    async def forget(self, guild_id, role_id):
        row = await CustomRole.filter(guild__id=guild_id, role_id=role_id).first()
        if row is not None:
            await row.delete()
