from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from rbb_bot.domain.custom_roles import RoleOwnership


@dataclass(frozen=True)
class CustomRoleSettings:
    """A guild's custom-role settings; the defaults match a guild with no stored row."""

    enabled: bool = False
    max_roles: int = 2


@dataclass(frozen=True)
class GuildRole:
    """The facts about a Discord role that decide whether the bot may delete it."""

    id: int
    holder_ids: frozenset[int]
    managed: bool = False
    default: bool = False


@dataclass(frozen=True)
class ColourPlacement:
    """Whether a new custom role's colour can show on its owner.

    Discord shows the colour of a member's highest coloured role, and a bot can only
    move roles below its own top role. So the one thing a guild may have to fix is a
    coloured role the member holds at or above the bot's: `blocked_by` is that role.
    """

    blocked_by: int | None = None
    forbidden: bool = False


class Refusal(Enum):
    DISABLED = "disabled"
    LIMIT_REACHED = "limit_reached"
    NAME_TOO_LONG = "name_too_long"
    NAME_IN_USE = "name_in_use"
    INVALID_COLOR = "invalid_color"
    NOT_OWNED = "not_owned"
    SHARED = "shared"
    INVALID_MAX = "invalid_max"


class CustomRoleRefused(Exception):
    """A request the feature turns down for a reason the requester can act on."""

    def __init__(self, refusal: Refusal, max_roles: int | None = None):
        super().__init__(refusal.value)
        self.refusal = refusal
        self.max_roles = max_roles


class RoleDeletionFailed(Exception):
    """Discord refused to delete a role that still exists.

    The Discord adapter raises this in place of Discord's own error, chained to it, so bulk
    cleanup can keep the ownership record for a later retry without depending on discord.py.
    """

    def __init__(self, role_id: int):
        super().__init__(f"role_id={role_id}")
        self.role_id = role_id


class CustomRoleRepository(Protocol):
    async def settings(self, guild_id: int) -> CustomRoleSettings: ...

    async def set_enabled(self, guild_id: int, enabled: bool) -> None: ...

    async def set_max_roles(self, guild_id: int, max_roles: int) -> None: ...

    async def record(self, guild_id: int, owner_id: int, role_id: int) -> None: ...

    async def list(
        self, guild_id: int, owner_id: int | None = None
    ) -> tuple[RoleOwnership, ...]: ...

    async def forget(self, guild_id: int, role_id: int) -> None: ...


class CustomRoleGuild(Protocol):
    """One Discord guild, as the custom-role use cases see it."""

    id: int

    async def roles(self, ids: tuple[int, ...]) -> dict[int, GuildRole]: ...

    def role_names(self) -> frozenset[str]: ...

    def sole_held_role_ids(self, member_id: int) -> frozenset[int]: ...

    async def create_role(self, name: str, color: int) -> int: ...

    async def assign(self, member_id: int, role_id: int) -> None: ...

    async def delete_role(self, role_id: int, reason: str) -> None: ...

    async def show_colour(self, role_id: int) -> ColourPlacement: ...
