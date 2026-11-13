import discord

from rbb_bot.application.custom_roles.contracts import GuildRole, RoleDeletionFailed


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

    async def place_on_top(self, role_id) -> bool:
        """Move a new role to the member's top position; False when Discord refuses."""
        if len(self.member.roles) == 1:
            return True
        try:
            top_pos = self.member.top_role.position
            await self.member.top_role.edit(position=top_pos - 1)
            await self._role(role_id).edit(position=top_pos)
        except discord.HTTPException:
            return False
        return True
