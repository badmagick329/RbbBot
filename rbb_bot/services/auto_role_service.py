import traceback
from dataclasses import dataclass
from typing import Iterable

import discord
from core.errors import AutoRoleServiceError
from core.result import Result
from models.auto_role import AutoRole


@dataclass
class ListAutoRolesResult:
    existing_roles: list[discord.Role]
    deleted_role_ids: list[int]


class AutoRoleService:
    @classmethod
    async def add_auto_role(
        cls, guild_id: int, role_id: int
    ) -> Result[str, AutoRoleServiceError]:
        try:
            saved_roles = await AutoRole.filter(guild_id=guild_id).values_list(
                "role_id", flat=True
            )
            if len(saved_roles) >= 5:
                return Result.Ok(
                    "You can only have a maximum of 5 auto roles per guild."
                )

            auto_role, created = await AutoRole.get_or_create(
                guild_id=guild_id, role_id=role_id
            )
            if not created:
                return Result.Ok("Role already exists in auto role list")
            created_role = auto_role.role
            # NOTE: This should never happen really happen
            if not created_role:
                return Result.Err(
                    AutoRoleServiceError(
                        f"Role ({auto_role.role_id}) not found for guild ({auto_role.guild_id})"
                    )
                )

            return Result.Ok(f"{created_role.mention} added to auto role list")
        except Exception as e:
            return Result.Err(AutoRoleServiceError(f"{e}\n{traceback.format_exc()}"))

    @classmethod
    async def remove_auto_role(
        cls, guild_id: int, role_id: int
    ) -> Result[str, AutoRoleServiceError]:
        try:
            auto_role = await AutoRole.get_or_none(guild_id=guild_id, role_id=role_id)
            if not auto_role:
                return Result.Ok("Role not found in auto role list")

            role_name = auto_role.role.name if auto_role.role else "Unknown Role"
            await auto_role.delete()
            return Result.Ok(f"{role_name} removed from auto role list")
        except Exception as e:
            return Result.Err(AutoRoleServiceError(f"Error removing auto role: {e}"))

    @classmethod
    async def remove_auto_roles(
        cls, guild_id: int, role_ids: list[int]
    ) -> Result[str, AutoRoleServiceError]:
        try:
            auto_roles = await AutoRole.filter(guild_id=guild_id, role_id__in=role_ids)
            if not auto_roles:
                return Result.Ok("No roles found in auto role list")
            role_names = [
                auto_role.role.name if auto_role.role else f"`[{auto_role.role_id}]`"
                for auto_role in auto_roles
            ]

            await AutoRole.filter(guild_id=guild_id, role_id__in=role_ids).delete()
            return Result.Ok(
                f"Removed roles: {', '.join(role_names)} from auto role list"
            )

        except Exception as e:
            return Result.Err(AutoRoleServiceError(f"Error removing auto roles: {e}"))

    @classmethod
    async def remove_all_auto_roles(
        cls, guild_id: int
    ) -> Result[str, AutoRoleServiceError]:
        try:
            await AutoRole.filter(guild_id=guild_id).delete()
            return Result.Ok("All auto roles removed.")
        except Exception as e:
            return Result.Err(
                AutoRoleServiceError(f"Error removing all auto roles: {e}")
            )

    @classmethod
    async def list_auto_roles(
        cls, guild_id: int
    ) -> Result[ListAutoRolesResult, AutoRoleServiceError]:
        try:
            auto_roles = await AutoRole.filter(guild_id=guild_id)
            existing_roles = []
            deleted_role_ids = []
            for auto_role in auto_roles:
                role = auto_role.role
                if role:
                    existing_roles.append(role)
                else:
                    deleted_role_ids.append(auto_role.role_id)

            return Result.Ok(
                ListAutoRolesResult(
                    existing_roles=existing_roles,
                    deleted_role_ids=deleted_role_ids,
                )
            )
        except Exception as e:
            return Result.Err(AutoRoleServiceError(f"{e}"))

    @classmethod
    async def apply_auto_roles(
        cls,
        guild_id: int,
        members: Iterable[discord.Member],
        include_bots: bool = False,
    ):
        try:
            auto_roles = await AutoRole.filter(guild_id=guild_id)
            roles = [r.role for r in auto_roles if r.role]
            members_and_missing_roles = {}
            for member in members:
                if member.bot and not include_bots:
                    continue
                member_roles = set(member.roles)
                missing_roles = [role for role in roles if role not in member_roles]
                if missing_roles:
                    members_and_missing_roles[member] = missing_roles

            if not members_and_missing_roles:
                return Result.Ok("No members missing auto roles.")

            errors = []
            successes = 0
            for member, missing_roles in members_and_missing_roles.items():
                try:
                    await member.add_roles(
                        *missing_roles, reason="Auto role assignment"
                    )
                    successes += 1

                except Exception as e:
                    errors.append(
                        f"Failed to add roles {', '.join(role.name for role in missing_roles)} "
                        f"to {member.display_name}: {e}"
                    )

            if not errors:
                return Result.Ok("All auto roles applied successfully.")

            return Result.Err(
                AutoRoleServiceError(
                    f"Applied {successes} auto roles with errors:\n{', '.join(errors)}"
                )
            )

        except Exception as e:
            return Result.Err(AutoRoleServiceError(f"{e}"))
