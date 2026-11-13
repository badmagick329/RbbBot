import discord

from rbb_bot.application.custom_roles.contracts import (
    ColourPlacement,
    GuildRole,
    RoleDeletionFailed,
)


class DiscordCustomRoles:
    """One command's or event's view of a Discord guild for the custom-role use cases.

    Built per invocation around the requesting member, so member checks read the same
    `Member` object discord.py handed the command. It remembers every `Role` it resolved
    or created, because a freshly created role is not in the guild cache yet.
    """

    def __init__(self, guild: discord.Guild, member: discord.Member | None = None):
        self.guild = guild
        self.member = member
        self._known: dict[int, discord.Role] = {}

    @property
    def id(self) -> int:
        return self.guild.id

    def _member(self, member_id):
        if self.member is not None and self.member.id == member_id:
            return self.member
        return self.guild.get_member(member_id)

    def _role(self, role_id):
        return self._known.get(role_id) or self.guild.get_role(role_id)

    async def roles(self, ids):
        # Role.members is derived from the member cache, not a Discord API count.
        if not self.guild.chunked:
            await self.guild.chunk()
        roles = {role.id: role for role in self.guild.roles}
        if any(role_id not in roles for role_id in ids):
            roles = {role.id: role for role in await self.guild.fetch_roles()}
        found = {}
        for role_id in ids:
            role = roles.get(role_id)
            if role is not None:
                self._known[role_id] = role
                found[role_id] = GuildRole(
                    role.id,
                    frozenset(member.id for member in role.members),
                    managed=role.managed,
                    default=role.is_default(),
                )
        return found

    def role_names(self):
        return frozenset(role.name for role in self.guild.roles)

    def sole_held_role_ids(self, member_id):
        return frozenset(
            role.id for role in self._member(member_id).roles if len(role.members) == 1
        )

    async def create_role(self, name, color):
        role = await self.guild.create_role(
            name=name,
            color=discord.Color(color),
            reason=f"Created by {self.member} ({self.member.id})",
        )
        self._known[role.id] = role
        return role.id

    async def assign(self, member_id, role_id):
        await self._member(member_id).add_roles(self._role(role_id))

    async def delete_role(self, role_id, reason):
        try:
            await self._role(role_id).delete(reason=reason)
        except discord.NotFound:
            pass
        except discord.HTTPException as error:
            raise RoleDeletionFailed(role_id) from error

    async def show_colour(self, role_id) -> ColourPlacement:
        """Move a new role directly above the member's highest coloured role.

        A custom role carries a colour and nothing else, so its position matters only
        relative to the member's other coloured roles; uncoloured roles above it are
        harmless and stay untouched. The roles between keep their order and slide down
        one place, which is how Discord represents an insertion.

        Positions come from a fresh fetch: creating the role just shifted the guild's
        other roles, and the cache may not have caught up.
        """
        fresh = {role.id: role for role in await self.guild.fetch_roles()}
        new = fresh[role_id]
        held = {role.id for role in self.member.roles} - {role_id}
        coloured = [
            role for role in fresh.values() if role.id in held and role.colour.value
        ]
        if not coloured:
            return ColourPlacement()
        highest = max(coloured, key=_rank)
        if _rank(highest) < _rank(new):
            return ColourPlacement()
        bot_top = max(
            (fresh[role.id] for role in self.guild.me.roles if role.id in fresh),
            key=_rank,
        )
        if highest.position >= bot_top.position:
            return ColourPlacement(blocked_by=highest.id)
        passed = sorted(
            (
                role
                for role in fresh.values()
                if _rank(new) < _rank(role) <= _rank(highest)
            ),
            key=_rank,
        )
        positions = {role: new.position + i for i, role in enumerate(passed)}
        positions[new] = new.position + len(passed)
        try:
            await self.guild.edit_role_positions(positions)
        except discord.Forbidden:
            return ColourPlacement(forbidden=True)
        return ColourPlacement()


def _rank(role):
    # Discord breaks position ties by ID, as discord.py's own role ordering does.
    return role.position, role.id
