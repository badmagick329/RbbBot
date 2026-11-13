import pytest
from tortoise import Tortoise

from rbb_bot.infrastructure.custom_roles.repository import (
    TortoiseCustomRoleRepository,
)
from rbb_bot.application.custom_roles.contracts import CustomRoleSettings
from rbb_bot.application.custom_roles.manage_roles import (
    CreateCustomRole,
    DeleteCustomRoles,
)
from rbb_bot.domain.custom_roles import RoleOwnership
from tests.test_custom_roles import FakeGuild
from rbb_bot.models import CustomRole, DiscordUser, Guild
from rbb_bot.infrastructure.privacy.user_data import UserDataService
from rbb_bot.infrastructure.database.lifecycle import initialize_empty_database
from rbb_bot.upgrade_database import upgrade
from tests.test_database_lifecycle import config, empty_schema

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_settings_reads_are_nonmutating_and_updates_keep_other_fields(
    test_database,
):
    repo = TortoiseCustomRoleRepository()
    assert await repo.settings(1) == CustomRoleSettings(False, 2)
    assert await Guild.all() == []

    await repo.set_max_roles(1, 4)
    await repo.set_enabled(1, True)
    await Guild.create(id=2, reminders_enabled=True)
    await repo.set_enabled(2, True)

    assert await repo.settings(1) == CustomRoleSettings(True, 4)
    assert await repo.settings(2) == CustomRoleSettings(True, 2)
    assert (await Guild.get(id=2)).reminders_enabled
    assert await Guild.all().count() == 2


async def test_owned_roles_are_created_and_cleaned_up_through_postgres(
    test_database,
):
    repo = TortoiseCustomRoleRepository()
    await repo.set_enabled(1, True)
    guild = FakeGuild()
    role_id = await CreateCustomRole(repo, guild).execute(10, "Mine", 0x123456)
    assert await repo.list(1, 10) == (RoleOwnership(role_id, 10),)

    cleanup = await DeleteCustomRoles(repo, guild).departed(10)

    assert cleanup.deleted == 1
    assert await CustomRole.all() == []


async def test_role_ownership_is_scoped_and_included_in_privacy_operations(
    test_database,
):
    first, second = await Guild.create(id=1), await Guild.create(id=2)
    repo = TortoiseCustomRoleRepository()
    await repo.record(1, 10, 100)
    await repo.record(2, 20, 200)
    assert await repo.list(1, 10) == (RoleOwnership(100, 10),)
    assert await repo.list(1, 20) == ()
    await repo.forget(2, 100)
    assert await CustomRole.filter(role_id=100).exists()
    assert (await UserDataService.export(10))["custom_roles"] == [
        {"role_id": 100, "guild_id": 1}
    ]
    await UserDataService.delete_user_data(10)
    assert not await CustomRole.filter(role_id=100).exists()
    assert await CustomRole.filter(role_id=200).exists()
    await second.delete()
    assert not await CustomRole.filter(role_id=200).exists()


async def test_existing_database_upgrade_adds_empty_ownership_table_and_preserves_data(
    test_database,
):
    await empty_schema()
    await initialize_empty_database()
    guild = await Guild.create(id=123, prefix="old-prefix")
    user = await DiscordUser.create(id=456, cached_username="saved")
    ciphertext = guild.prefix_ciphertext
    await upgrade(config())
    await Tortoise.init(config=config())
    assert await CustomRole.all() == []
    stored = await Guild.get(id=123)
    assert stored.prefix_ciphertext == ciphertext
    assert stored.prefix == "old-prefix"
    assert (await DiscordUser.get(id=456)).cached_username == "saved"
    repo = TortoiseCustomRoleRepository()
    await repo.record(123, 456, 999)
    assert await repo.list(123) == (RoleOwnership(999, 456),)
    await upgrade(config())
    await Tortoise.init(config=config())
    assert await repo.list(123) == (RoleOwnership(999, 456),)
