from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from rbb_bot.cogs.roles_cog import RolesCog
from rbb_bot.domain.custom_roles import RoleOwnership


def role(role_id, holders=()):
    return SimpleNamespace(
        id=role_id,
        members=[SimpleNamespace(id=i) for i in holders],
        managed=False,
        is_default=lambda: False,
        delete=AsyncMock(),
    )


def cog_and_guild(records, roles):
    cog = RolesCog(Mock())
    cog.ownership = SimpleNamespace(
        list=AsyncMock(return_value=records), forget=AsyncMock()
    )
    guild = SimpleNamespace(
        id=1, roles=roles, chunked=True, fetch_roles=AsyncMock(return_value=roles)
    )
    return cog, guild


@pytest.mark.asyncio
async def test_member_cannot_delete_untracked_role():
    manual = role(10, [2])
    cog, guild = cog_and_guild([], [manual])
    ctx = SimpleNamespace(
        interaction=None, guild=guild, author=SimpleNamespace(id=2), send=AsyncMock()
    )
    with patch(
        "rbb_bot.cogs.roles_cog.Guild.get_or_create",
        new=AsyncMock(return_value=(SimpleNamespace(custom_roles_enabled=True), False)),
    ):
        await RolesCog.remove.callback(cog, ctx, role=manual)
    manual.delete.assert_not_awaited()
    assert "recorded as yours" in ctx.send.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "holders,deleted", [([], True), ([2], True), ([3], False), ([2, 3], False)]
)
async def test_bulk_cleanup_only_deletes_recorded_roles_without_other_holders(
    holders, deleted
):
    owned, manual = role(10, holders), role(11)
    cog, guild = cog_and_guild([RoleOwnership(10, 2)], [owned, manual])
    assert await cog._delete_tracked_roles(guild) == int(deleted)
    assert owned.delete.await_count == int(deleted)
    manual.delete.assert_not_awaited()
    assert cog.ownership.forget.await_count == int(deleted)


@pytest.mark.asyncio
async def test_prune_keeps_recorded_roles_still_in_use():
    owned = role(10, [2])
    cog, guild = cog_and_guild([RoleOwnership(10, 2)], [owned])
    assert await cog._delete_tracked_roles(guild, unused_only=True) == 0
    owned.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_leave_cleanup_uses_discord_event_and_continues_after_forbidden():
    failing, working = role(10), role(11)
    failing.delete.side_effect = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"), "Missing permissions"
    )
    cog, guild = cog_and_guild(
        [RoleOwnership(10, 2), RoleOwnership(11, 2)], [failing, working]
    )
    member = SimpleNamespace(id=2, guild=guild)
    assert ("on_member_remove", "on_member_remove") in cog.__cog_listeners__
    with patch(
        "rbb_bot.cogs.roles_cog.Guild.get_or_none",
        new=AsyncMock(return_value=SimpleNamespace(custom_roles_enabled=True)),
    ):
        await cog.on_member_remove(member)
    cog.ownership.list.assert_awaited_once_with(1, 2)
    cog.ownership.forget.assert_awaited_once_with(1, 11)
    working.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_miss_fetches_roles_and_full_members_before_deletion():
    owned = role(10, [2, 3])
    cog, guild = cog_and_guild([RoleOwnership(10, 2)], [])
    guild.chunked = False
    guild.chunk = AsyncMock()
    guild.fetch_roles.return_value = [owned]
    assert await cog._delete_tracked_roles(guild) == 0
    guild.chunk.assert_awaited_once()
    guild.fetch_roles.assert_awaited_once()
    owned.delete.assert_not_awaited()
    cog.ownership.forget.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("holders,deleted", [([2], True), ([2, 3], False)])
async def test_owner_can_remove_only_their_unshared_recorded_role(holders, deleted):
    owned = role(10, holders)
    cog, guild = cog_and_guild([RoleOwnership(10, 2)], [owned])
    ctx = SimpleNamespace(
        interaction=None, guild=guild, author=SimpleNamespace(id=2), send=AsyncMock()
    )
    with patch(
        "rbb_bot.cogs.roles_cog.Guild.get_or_create",
        new=AsyncMock(return_value=(SimpleNamespace(custom_roles_enabled=True), False)),
    ):
        await RolesCog.remove.callback(cog, ctx, role=owned)
    cog.ownership.list.assert_awaited_once_with(1, 2)
    assert owned.delete.await_count == int(deleted)


@pytest.mark.asyncio
@pytest.mark.parametrize("record_fails", [False, True])
async def test_creation_records_ownership_before_assigning_role(record_fails):
    created = role(10)
    created.mention = "<@&10>"
    cog, guild = cog_and_guild([], [])
    guild.create_role = AsyncMock(return_value=created)
    cog.ownership.record = AsyncMock(
        side_effect=RuntimeError("database failed") if record_fails else None
    )
    everyone = SimpleNamespace(id=1, members=[1, 2])
    author = SimpleNamespace(id=2, roles=[everyone], add_roles=AsyncMock())
    ctx = SimpleNamespace(
        interaction=None, guild=guild, author=author, send=AsyncMock()
    )
    with patch(
        "rbb_bot.cogs.roles_cog.Guild.get_or_create",
        new=AsyncMock(
            return_value=(
                SimpleNamespace(custom_roles_enabled=True, max_custom_roles=2),
                False,
            )
        ),
    ):
        if record_fails:
            with pytest.raises(RuntimeError, match="database failed"):
                await RolesCog.add.callback(cog, ctx, "#123456", name="Custom")
        else:
            await RolesCog.add.callback(cog, ctx, "#123456", name="Custom")
    cog.ownership.record.assert_awaited_once_with(1, 2, 10)
    assert created.delete.await_count == int(record_fails)
    assert author.add_roles.await_count == int(not record_fails)
