from dataclasses import dataclass

from rbb_bot.application.custom_roles.contracts import (
    CustomRoleGuild,
    CustomRoleRefused,
    CustomRoleRepository,
    GuildRole,
    Refusal,
    RoleDeletionFailed,
)
from rbb_bot.domain.custom_roles import ROLE_NAME_LIMIT, RoleOwnership

DELETE_REASON = "Removing recorded bot-created custom role"
UNRECORDED_REASON = "Could not record custom role ownership"


@dataclass(frozen=True)
class RoleCleanup:
    deleted: int
    failures: tuple[RoleDeletionFailed, ...]


async def live_owned_roles(
    repository: CustomRoleRepository,
    guild: CustomRoleGuild,
    owner_id: int | None = None,
) -> tuple[tuple[RoleOwnership, GuildRole], ...]:
    """Pair ownership records with their Discord roles.

    Records outlive roles deleted directly in Discord; forgetting those here keeps role
    limits and cleanup counting only roles that still exist.
    """
    records = await repository.list(guild.id, owner_id)
    roles = await guild.roles(tuple(record.role_id for record in records))
    live = []
    for record in records:
        role = roles.get(record.role_id)
        if role is None:
            await repository.forget(guild.id, record.role_id)
        else:
            live.append((record, role))
    return tuple(live)


def _deletable(record: RoleOwnership, role: GuildRole) -> bool:
    return record.permits_deletion(
        role.holder_ids, managed=role.managed, default=role.default
    )


async def _delete(repository, guild, role_id):
    await guild.delete_role(role_id, DELETE_REASON)
    await repository.forget(guild.id, role_id)


class CreateCustomRole:
    def __init__(self, repository: CustomRoleRepository, guild: CustomRoleGuild):
        self.repository = repository
        self.guild = guild

    async def execute(self, owner_id: int, name: str, color: int | None) -> int:
        """Create, record and assign a member's role, returning its ID.

        The record is written before the role is assigned and the role is deleted if
        recording fails, so the bot never hands out a role it could not later remove.
        """
        settings = await self.repository.settings(self.guild.id)
        if not settings.enabled:
            raise CustomRoleRefused(Refusal.DISABLED)
        owned = await live_owned_roles(self.repository, self.guild, owner_id)
        # Count untracked sole-holder roles too: erasing ownership data must not
        # let a member bypass the server's role limit.
        held = {record.role_id for record, _ in owned} | self.guild.sole_held_role_ids(
            owner_id
        )
        if len(held) >= settings.max_roles:
            raise CustomRoleRefused(Refusal.LIMIT_REACHED, settings.max_roles)
        name = name.strip()
        if len(name) > ROLE_NAME_LIMIT:
            raise CustomRoleRefused(Refusal.NAME_TOO_LONG)
        if name in self.guild.role_names():
            raise CustomRoleRefused(Refusal.NAME_IN_USE)
        if color is None:
            raise CustomRoleRefused(Refusal.INVALID_COLOR)

        role_id = await self.guild.create_role(name, color)
        try:
            await self.repository.record(self.guild.id, owner_id, role_id)
        except Exception:
            await self.guild.delete_role(role_id, UNRECORDED_REASON)
            raise
        await self.guild.assign(owner_id, role_id)
        return role_id


class RemoveCustomRole:
    def __init__(self, repository: CustomRoleRepository, guild: CustomRoleGuild):
        self.repository = repository
        self.guild = guild

    async def execute(self, owner_id: int, role_id: int) -> None:
        settings = await self.repository.settings(self.guild.id)
        if not settings.enabled:
            raise CustomRoleRefused(Refusal.DISABLED)
        owned = await live_owned_roles(self.repository, self.guild, owner_id)
        match = next(
            ((record, role) for record, role in owned if role.id == role_id), None
        )
        if match is None:
            raise CustomRoleRefused(Refusal.NOT_OWNED)
        if not _deletable(*match):
            raise CustomRoleRefused(Refusal.SHARED)
        await _delete(self.repository, self.guild, role_id)


class DeleteCustomRoles:
    """Bulk cleanup that deletes only recorded roles nobody but their owner holds.

    One role Discord refuses to delete must not stop the rest; its record is kept so a
    later prune can retry.
    """

    def __init__(self, repository: CustomRoleRepository, guild: CustomRoleGuild):
        self.repository = repository
        self.guild = guild

    async def execute(
        self, owner_id: int | None = None, unused_only: bool = False
    ) -> RoleCleanup:
        deleted = 0
        failures = []
        for record, role in await live_owned_roles(
            self.repository, self.guild, owner_id
        ):
            if not _deletable(record, role):
                continue
            if unused_only and role.holder_ids:
                continue
            try:
                await _delete(self.repository, self.guild, role.id)
                deleted += 1
            except RoleDeletionFailed as failure:
                failures.append(failure)
        return RoleCleanup(deleted, tuple(failures))

    async def departed(self, member_id: int) -> RoleCleanup | None:
        """Remove a departing member's roles, only where the guild has the feature enabled."""
        settings = await self.repository.settings(self.guild.id)
        if not settings.enabled:
            return None
        return await self.execute(owner_id=member_id)
