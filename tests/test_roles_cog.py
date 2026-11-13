from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from rbb_bot.application.custom_roles.contracts import RoleDeletionFailed
from rbb_bot.application.custom_roles.manage_roles import DeleteCustomRoles
from rbb_bot.cogs.roles_cog import RolesCog
from rbb_bot.domain.custom_roles import RoleOwnership
from rbb_bot.infrastructure.custom_roles.discord_guild import DiscordCustomRoles
from tests.test_custom_roles import FakeRepository

pytestmark = pytest.mark.asyncio


def http_error(kind, status):
    return kind(SimpleNamespace(status=status, reason="refused"), "refused")


def discord_role(role_id, holders=(), name="role"):
    return SimpleNamespace(
        id=role_id,
        name=name,
        members=[SimpleNamespace(id=i) for i in holders],
        managed=False,
        is_default=lambda: False,
        delete=AsyncMock(),
        edit=AsyncMock(),
        position=1,
    )


def discord_guild(roles, chunked=True):
    return SimpleNamespace(
        id=1,
        roles=list(roles),
        chunked=chunked,
        chunk=AsyncMock(),
        fetch_roles=AsyncMock(return_value=list(roles)),
        get_role=lambda role_id: None,
        get_member=lambda member_id: None,
    )


def cog_with(repository):
    bot = Mock()
    cog = RolesCog(bot)
    cog.repository = repository
    return cog


def context(guild, author):
    return SimpleNamespace(
        interaction=None, guild=guild, author=author, prefix="!", send=AsyncMock()
    )


async def test_cache_miss_loads_members_and_fetches_roles_before_deciding():
    shared = discord_role(10, holders=[2, 3])
    guild = discord_guild([], chunked=False)
    guild.fetch_roles.return_value = [shared]
    repository = FakeRepository([RoleOwnership(10, 2)])

    cleanup = await DeleteCustomRoles(repository, DiscordCustomRoles(guild)).execute()

    guild.chunk.assert_awaited_once()
    guild.fetch_roles.assert_awaited_once()
    assert cleanup.deleted == 0
    shared.delete.assert_not_awaited()
    assert repository.records == [RoleOwnership(10, 2)]


async def test_deleting_an_already_deleted_role_still_forgets_it():
    gone = discord_role(10)
    gone.delete.side_effect = http_error(discord.NotFound, 404)
    repository = FakeRepository([RoleOwnership(10, 2)])

    cleanup = await DeleteCustomRoles(
        repository, DiscordCustomRoles(discord_guild([gone]))
    ).execute()

    assert cleanup.deleted == 1
    assert repository.records == []


async def test_remove_surfaces_discords_own_refusal_to_the_error_handler():
    owned = discord_role(10, holders=[2])
    forbidden = http_error(discord.Forbidden, 403)
    owned.delete.side_effect = forbidden
    cog = cog_with(FakeRepository([RoleOwnership(10, 2)]))
    ctx = context(discord_guild([owned]), SimpleNamespace(id=2, roles=[]))

    with pytest.raises(discord.Forbidden) as raised:
        await RolesCog.remove.callback(cog, ctx, role=owned)

    assert raised.value is forbidden
    ctx.send.assert_not_awaited()


async def test_member_leave_deletes_their_roles_and_logs_refusals():
    refused, deletable = discord_role(10), discord_role(11)
    refused.delete.side_effect = http_error(discord.Forbidden, 403)
    repository = FakeRepository([RoleOwnership(10, 2), RoleOwnership(11, 2)])
    cog = cog_with(repository)
    member = SimpleNamespace(id=2, guild=discord_guild([refused, deletable]))

    assert ("on_member_remove", "on_member_remove") in cog.__cog_listeners__
    await cog.on_member_remove(member)

    deletable.delete.assert_awaited_once()
    assert repository.records == [RoleOwnership(10, 2)]
    logged = cog.bot.logger.error.call_args
    assert logged.args[1:] == (1, 10)
    assert isinstance(logged.kwargs["exc_info"], RoleDeletionFailed)


async def test_add_creates_assigns_and_reports_a_refused_reposition():
    everyone, top = discord_role(1), discord_role(5)
    top.edit.side_effect = http_error(discord.Forbidden, 403)
    created = discord_role(42)
    guild = discord_guild([everyone, top])
    guild.create_role = AsyncMock(return_value=created)
    author = SimpleNamespace(
        id=2, roles=[everyone, top], top_role=top, add_roles=AsyncMock()
    )
    repository = FakeRepository()
    ctx = context(guild, author)

    await RolesCog.add.callback(cog_with(repository), ctx, "red", name="Mine")

    assert guild.create_role.call_args.kwargs["color"] == discord.Color(0xFF0000)
    author.add_roles.assert_awaited_once_with(created)
    assert repository.records == [RoleOwnership(42, 2)]
    sent = [call.args[0] for call in ctx.send.await_args_list]
    assert sent[0] == "Created role <@&42>"
    assert "permission to reposition" in sent[1]


async def test_add_with_an_unknown_color_replies_with_the_color_help_embed():
    guild = discord_guild([])
    guild.create_role = AsyncMock()
    ctx = context(guild, SimpleNamespace(id=2, roles=[]))

    await RolesCog.add.callback(
        cog_with(FakeRepository()), ctx, "notacolor", name="Mine"
    )

    guild.create_role.assert_not_awaited()
    embed = ctx.send.call_args.kwargs["embed"]
    assert "!roles colors" in embed.description
