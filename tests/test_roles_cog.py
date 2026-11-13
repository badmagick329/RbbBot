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


class PlacedRole(SimpleNamespace):
    # Role positions are sent to Discord as a mapping keyed by role.
    __hash__ = object.__hash__


def placed_role(role_id, position, colour=0):
    return PlacedRole(
        id=role_id,
        name=f"role-{role_id}",
        members=[],
        position=position,
        colour=discord.Colour(colour),
    )


async def add_role(member_roles, bot_top, others=(), move_error=None):
    """Run `roles add` for a member; role 42 is the one Discord creates at the bottom.

    Returns the bot's replies and the role positions it asked Discord to set.
    """
    everyone, created = placed_role(1, 0), placed_role(42, 1, 0xFF0000)
    roles = [everyone, created, *member_roles, bot_top, *others]
    guild = discord_guild(roles)
    guild.create_role = AsyncMock(return_value=created)
    guild.me = SimpleNamespace(roles=[everyone, bot_top])
    guild.edit_role_positions = AsyncMock(side_effect=move_error)
    author = SimpleNamespace(
        id=2, roles=[everyone, *member_roles], add_roles=AsyncMock()
    )
    repository = FakeRepository()
    ctx = context(guild, author)

    await RolesCog.add.callback(cog_with(repository), ctx, "red", name="Mine")

    assert guild.create_role.call_args.kwargs["color"] == discord.Color(0xFF0000)
    author.add_roles.assert_awaited_once_with(created)
    assert repository.records == [RoleOwnership(42, 2)]
    moves = [
        {role.id: position for role, position in call.args[0].items()}
        for call in guild.edit_role_positions.await_args_list
    ]
    return [call.args[0] for call in ctx.send.await_args_list], moves


async def test_add_moves_nothing_for_a_member_with_no_coloured_role():
    # An uncoloured role above the bot (an admin's) cannot hide the new colour.
    admin = placed_role(5, 9)

    sent, moves = await add_role([admin], bot_top=placed_role(6, 4))

    assert sent == ["Created role <@&42>"]
    assert moves == []


async def test_add_places_the_role_directly_above_the_members_highest_coloured_role():
    low, high = placed_role(5, 2, 0x00FF00), placed_role(6, 4, 0x0000FF)
    plain_above = placed_role(7, 5)
    unrelated = placed_role(8, 3)

    sent, moves = await add_role(
        [low, high, plain_above], bot_top=placed_role(9, 6), others=[unrelated]
    )

    assert sent == ["Created role <@&42>"]
    # The passed roles keep their order one place down; nothing above is touched.
    assert moves == [{5: 1, 8: 2, 6: 3, 42: 4}]


async def test_add_keeps_the_role_and_names_a_coloured_role_the_bot_cannot_pass():
    blocking = placed_role(5, 6, 0x00FF00)

    sent, moves = await add_role([blocking], bot_top=placed_role(6, 4))

    assert sent[0] == "Created role <@&42>"
    assert "<@&5>" in sent[1] and "above" in sent[1]
    assert moves == []


async def test_add_reports_a_missing_permission_only_when_discord_forbids_the_move():
    coloured = placed_role(5, 2, 0x00FF00)

    sent, _ = await add_role(
        [coloured],
        bot_top=placed_role(6, 4),
        move_error=http_error(discord.Forbidden, 403),
    )

    assert "`manage roles`" in sent[1]


async def test_add_leaves_other_discord_failures_to_the_error_handler():
    coloured = placed_role(5, 2, 0x00FF00)

    with pytest.raises(discord.HTTPException) as raised:
        await add_role(
            [coloured],
            bot_top=placed_role(6, 4),
            move_error=http_error(discord.HTTPException, 500),
        )

    assert not isinstance(raised.value, discord.Forbidden)


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
