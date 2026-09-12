import pytest
from tortoise import Tortoise

from rbb_bot.infrastructure.custom_roles.repository import CustomRoleRepository
from rbb_bot.domain.custom_roles import RoleOwnership
from rbb_bot.models import CustomRole, DiscordUser, Guild
from rbb_bot.infrastructure.privacy.user_data import UserDataService
from rbb_bot.infrastructure.database.lifecycle import initialize_empty_database
from rbb_bot.upgrade_database import upgrade
from tests.test_database_lifecycle import config, empty_schema

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_role_ownership_is_scoped_and_included_in_privacy_operations(
    test_database,
):
    first, second = await Guild.create(id=1), await Guild.create(id=2)
    repo = CustomRoleRepository()
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
    repo = CustomRoleRepository()
    await repo.record(123, 456, 999)
    assert await repo.list(123) == (RoleOwnership(999, 456),)
    await upgrade(config())
    await Tortoise.init(config=config())
    assert await repo.list(123) == (RoleOwnership(999, 456),)
