import traceback

import discord
from core.errors import AutoRoleServiceError
from core.result import Result
from models.auto_role import AutoRole


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
    ) -> Result[list[discord.Role], AutoRoleServiceError]:
        try:
            auto_roles = await AutoRole.filter(guild_id=guild_id)
            roles = [role.role for role in auto_roles if role.role]
            return Result.Ok(roles)
        except Exception as e:
            return Result.Err(AutoRoleServiceError(f"Error retrieving auto roles: {e}"))
