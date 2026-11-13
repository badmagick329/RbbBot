import pytest

from rbb_bot.application.custom_roles.configure import ConfigureCustomRoles
from rbb_bot.application.custom_roles.contracts import (
    CustomRoleRefused,
    CustomRoleSettings,
    GuildRole,
    Refusal,
    RoleDeletionFailed,
)
from rbb_bot.application.custom_roles.manage_roles import (
    CreateCustomRole,
    DeleteCustomRoles,
    RemoveCustomRole,
)
from rbb_bot.domain.custom_roles import RoleOwnership

pytestmark = pytest.mark.asyncio

OWNER = 2
OTHER = 3


class FakeRepository:
    def __init__(self, records=(), enabled=True, max_roles=2, fail_record=False):
        self.stored = CustomRoleSettings(enabled, max_roles)
        self.records = list(records)
        self.fail_record = fail_record

    async def settings(self, guild_id):
        return self.stored

    async def set_enabled(self, guild_id, enabled):
        self.stored = CustomRoleSettings(enabled, self.stored.max_roles)

    async def set_max_roles(self, guild_id, max_roles):
        self.stored = CustomRoleSettings(self.stored.enabled, max_roles)

    async def record(self, guild_id, owner_id, role_id):
        if self.fail_record:
            raise RuntimeError("database failed")
        self.records.append(RoleOwnership(role_id, owner_id))

    async def list(self, guild_id, owner_id=None):
        return tuple(
            record
            for record in self.records
            if owner_id is None or record.owner_id == owner_id
        )

    async def forget(self, guild_id, role_id):
        self.records = [r for r in self.records if r.role_id != role_id]


class FakeGuild:
    id = 1

    def __init__(self, roles=(), names=(), sole_held=(), refuse=()):
        self.live = {role.id: role for role in roles}
        self.names = frozenset(names)
        self.sole_held = frozenset(sole_held)
        self.refuse = set(refuse)
        self.created = []
        self.assigned = []
        self.deleted = []

    async def roles(self, ids):
        return {i: self.live[i] for i in ids if i in self.live}

    def role_names(self):
        return self.names

    def sole_held_role_ids(self, member_id):
        return self.sole_held

    async def create_role(self, name, color):
        role = GuildRole(100 + len(self.created), frozenset())
        self.created.append((name, color))
        self.live[role.id] = role
        return role.id

    async def assign(self, member_id, role_id):
        self.assigned.append((member_id, role_id))

    async def delete_role(self, role_id, reason):
        if role_id in self.refuse:
            raise RoleDeletionFailed(role_id)
        self.deleted.append(role_id)
        self.live.pop(role_id, None)


def role(role_id, *holders):
    return GuildRole(role_id, frozenset(holders))


async def refusal_of(call):
    with pytest.raises(CustomRoleRefused) as caught:
        await call
    return caught.value


async def test_member_cannot_remove_a_role_without_their_ownership_record():
    repository = FakeRepository([RoleOwnership(11, OTHER)])
    guild = FakeGuild([role(10, OWNER), role(11, OTHER)])

    for role_id in (10, 11):
        refusal = await refusal_of(
            RemoveCustomRole(repository, guild).execute(OWNER, role_id)
        )
        assert refusal.refusal is Refusal.NOT_OWNED
    assert guild.deleted == []


@pytest.mark.parametrize(
    "holders,deleted", [((), True), ((OWNER,), True), ((OWNER, OTHER), False)]
)
async def test_owner_removes_only_their_unshared_recorded_role(holders, deleted):
    repository = FakeRepository([RoleOwnership(10, OWNER)])
    guild = FakeGuild([role(10, *holders)])
    remove = RemoveCustomRole(repository, guild).execute(OWNER, 10)

    if deleted:
        await remove
        assert guild.deleted == [10]
        assert repository.records == []
    else:
        assert (await refusal_of(remove)).refusal is Refusal.SHARED
        assert guild.deleted == []
        assert repository.records == [RoleOwnership(10, OWNER)]


async def test_remove_and_create_are_refused_while_disabled():
    repository = FakeRepository([RoleOwnership(10, OWNER)], enabled=False)
    guild = FakeGuild([role(10, OWNER)])

    removal = await refusal_of(RemoveCustomRole(repository, guild).execute(OWNER, 10))
    creation = await refusal_of(
        CreateCustomRole(repository, guild).execute(OWNER, "Name", 0x123456)
    )

    assert removal.refusal is creation.refusal is Refusal.DISABLED
    assert guild.deleted == guild.created == []


@pytest.mark.parametrize(
    "holders,deleted",
    [((), True), ((OWNER,), True), ((OTHER,), False), ((OWNER, OTHER), False)],
)
async def test_cleanup_deletes_only_recorded_roles_without_other_holders(
    holders, deleted
):
    repository = FakeRepository([RoleOwnership(10, OWNER)])
    guild = FakeGuild([role(10, *holders), role(11)])

    cleanup = await DeleteCustomRoles(repository, guild).execute()

    assert cleanup.deleted == int(deleted)
    assert guild.deleted == ([10] if deleted else [])
    assert len(repository.records) == int(not deleted)


async def test_prune_keeps_recorded_roles_still_in_use():
    repository = FakeRepository([RoleOwnership(10, OWNER), RoleOwnership(11, OWNER)])
    guild = FakeGuild([role(10, OWNER), role(11)])

    cleanup = await DeleteCustomRoles(repository, guild).execute(unused_only=True)

    assert cleanup.deleted == 1
    assert guild.deleted == [11]


async def test_records_of_roles_deleted_in_discord_are_forgotten():
    repository = FakeRepository([RoleOwnership(10, OWNER), RoleOwnership(11, OWNER)])
    guild = FakeGuild([role(11, OWNER, OTHER)])

    cleanup = await DeleteCustomRoles(repository, guild).execute()

    assert cleanup.deleted == 0
    assert repository.records == [RoleOwnership(11, OWNER)]


async def test_departed_member_cleanup_continues_after_a_refused_deletion():
    repository = FakeRepository(
        [
            RoleOwnership(10, OWNER),
            RoleOwnership(11, OWNER),
            RoleOwnership(12, OTHER),
        ]
    )
    guild = FakeGuild([role(10), role(11), role(12)], refuse={10})

    cleanup = await DeleteCustomRoles(repository, guild).departed(OWNER)

    assert cleanup.deleted == 1
    assert [failure.role_id for failure in cleanup.failures] == [10]
    assert guild.deleted == [11]
    # The refused role keeps its record so a later prune can retry.
    assert repository.records == [RoleOwnership(10, OWNER), RoleOwnership(12, OTHER)]


async def test_departed_member_cleanup_does_nothing_while_disabled():
    repository = FakeRepository([RoleOwnership(10, OWNER)], enabled=False)
    guild = FakeGuild([role(10)])

    assert await DeleteCustomRoles(repository, guild).departed(OWNER) is None
    assert guild.deleted == []


async def test_creation_records_ownership_then_assigns_the_role():
    repository = FakeRepository()
    guild = FakeGuild()

    role_id = await CreateCustomRole(repository, guild).execute(
        OWNER, "  Custom  ", 0x123456
    )

    assert guild.created == [("Custom", 0x123456)]
    assert repository.records == [RoleOwnership(role_id, OWNER)]
    assert guild.assigned == [(OWNER, role_id)]


async def test_creation_deletes_the_role_when_ownership_cannot_be_recorded():
    repository = FakeRepository(fail_record=True)
    guild = FakeGuild()

    with pytest.raises(RuntimeError, match="database failed"):
        await CreateCustomRole(repository, guild).execute(OWNER, "Custom", 0x123456)

    assert len(guild.created) == 1
    assert guild.deleted == [100]
    assert guild.assigned == []


async def test_role_limit_counts_untracked_roles_the_member_holds_alone():
    repository = FakeRepository([RoleOwnership(10, OWNER)], max_roles=2)
    guild = FakeGuild([role(10, OWNER)], sole_held={10, 20})

    refusal = await refusal_of(
        CreateCustomRole(repository, guild).execute(OWNER, "Custom", 0x123456)
    )

    assert refusal.refusal is Refusal.LIMIT_REACHED
    assert refusal.max_roles == 2
    assert guild.created == []


@pytest.mark.parametrize(
    "name,color,refusal",
    [
        ("x" * 101, None, Refusal.NAME_TOO_LONG),
        ("Taken", None, Refusal.NAME_IN_USE),
        ("Custom", None, Refusal.INVALID_COLOR),
    ],
)
async def test_creation_refuses_bad_names_before_bad_colors(name, color, refusal):
    guild = FakeGuild(names={"Taken"})

    caught = await refusal_of(
        CreateCustomRole(FakeRepository(), guild).execute(OWNER, name, color)
    )

    assert caught.refusal is refusal
    assert guild.created == []


async def test_a_100_character_name_is_accepted():
    guild = FakeGuild()

    await CreateCustomRole(FakeRepository(), guild).execute(OWNER, "x" * 100, 0)

    assert guild.created == [("x" * 100, 0)]


@pytest.mark.parametrize("max_roles", [0, 6])
async def test_max_roles_outside_one_to_five_is_refused(max_roles):
    repository = FakeRepository()

    refusal = await refusal_of(
        ConfigureCustomRoles(repository).set_max_roles(1, max_roles)
    )

    assert refusal.refusal is Refusal.INVALID_MAX
    assert repository.stored.max_roles == 2


async def test_configuration_stores_enabled_flag_and_limit():
    repository = FakeRepository(enabled=False)
    configure = ConfigureCustomRoles(repository)

    await configure.enable(1, True)
    await configure.set_max_roles(1, 5)

    assert repository.stored == CustomRoleSettings(True, 5)
