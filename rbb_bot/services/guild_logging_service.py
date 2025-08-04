import traceback
from dataclasses import dataclass
from typing import Literal

import discord
from core.errors import GuildLoggingServiceError
from core.result import Result
from models.guild import Guild
from models.guild_logging import GuildLogging


@dataclass
class GuildLoggingConfig:
    channel: str
    member_join: bool
    member_leave: bool
    message_removed: bool
    message_edited: bool


class GuildLoggingService:
    @staticmethod
    async def enable(
        guild: discord.Guild, channel: discord.TextChannel
    ) -> Result[str, GuildLoggingServiceError]:
        try:
            guild_model, _ = await Guild.get_or_create(id=guild.id)

            guild_logging, created = await GuildLogging.get_or_create(
                guild_model_id=guild_model._id
            )
            if created:
                guild_logging.channel_id = channel.id  # type: ignore
                await guild_logging.save()
                return Result.Ok(f"Logging enabled for {channel.mention}.")

            if guild_logging.channel_id == channel.id:
                return Result.Ok("Logging is already enabled in this channel.")

            guild_logging.channel_id = channel.id  # type: ignore
            await guild_logging.save()
            return Result.Ok(f"Logging channel changed to {channel.mention}.")
        except Exception as e:
            return Result.Err(GuildLoggingServiceError(f"Unexpected error: {e}"))

    @staticmethod
    async def disable(guild: discord.Guild) -> Result[str, GuildLoggingServiceError]:
        guild_model: Guild | None = None
        try:
            guild_model, _ = await Guild.get_or_create(id=guild.id)
        except Exception as e:
            return Result.Err(GuildLoggingServiceError(f"Error retrieving guild: {e}"))

        try:
            guild_logging = await GuildLogging.get_or_none(
                guild_model_id=guild_model._id
            )
            if not guild_logging:
                return Result.Ok("Logging is not enabled for this guild.")

            if guild_logging.is_disabled:
                return Result.Ok("Logging is already disabled for this guild.")

            await guild_logging.disable()
            return Result.Ok("Logging disabled for this guild.")

        except Exception as e:
            return Result.Err(GuildLoggingServiceError(f"Unexpected error: {e}"))

    @staticmethod
    async def setup(
        guild: discord.Guild,
        member_join: bool | None,
        member_leave: bool | None,
        message_removed: bool | None,
        message_edited: bool | None,
    ) -> Result[str, GuildLoggingServiceError]:
        if all(
            [
                member_join is None,
                member_leave is None,
                message_removed is None,
                message_edited is None,
            ]
        ):
            return Result.Ok(
                "Please specify at least one logging option to enable or disable."
            )

        try:
            guild_model, _ = await Guild.get_or_create(id=guild.id)

            guild_logging, _ = await GuildLogging.get_or_create(
                guild_model_id=guild_model._id
            )
            if member_join is not None:
                guild_logging.member_join_enabled = member_join  # type: ignore
            if member_leave is not None:
                guild_logging.member_leave_enabled = member_leave  # type: ignore
            if message_removed is not None:
                guild_logging.message_removed_enabled = message_removed  # type: ignore
            if message_edited is not None:
                guild_logging.message_edited_enabled = message_edited  # type: ignore

            await guild_logging.save()
            message = "Guild logging flags updated successfully."
            if guild_logging.channel_id is None:
                message += " Please set a logging channel using the `enable` command."

            return Result.Ok(message)
        except Exception as e:
            return Result.Err(
                GuildLoggingServiceError(f"Error updating guild logging flags:\n{e}")
            )

    @staticmethod
    async def show(
        guild: discord.Guild,
    ) -> Result[(GuildLoggingConfig | None), GuildLoggingServiceError]:
        try:
            guild_model, _ = await Guild.get_or_create(id=guild.id)

            guild_logging = await GuildLogging.get_or_none(
                guild_model_id=guild_model._id
            )
            if not guild_logging:
                return Result.Ok(None)

            return Result.Ok(
                GuildLoggingConfig(
                    channel=guild_logging.channel_mention or "None",
                    member_join=guild_logging.member_join_enabled,
                    member_leave=guild_logging.member_leave_enabled,
                    message_removed=guild_logging.message_removed_enabled,
                    message_edited=guild_logging.message_edited_enabled,
                )
            )

        except Exception as e:
            return Result.Err(
                GuildLoggingServiceError(f"Error retrieving logging config: {e}")
            )

    @classmethod
    async def logging_channel_for(
        cls,
        guild: discord.Guild,
        flag: Literal[
            "member_join", "member_leave", "message_removed", "message_edited"
        ],
    ) -> Result[discord.TextChannel | None, GuildLoggingServiceError]:
        try:
            guild_model = await Guild.get_or_none(id=guild.id)
            if not guild_model:
                return Result.Ok(None)

            guild_logging = await GuildLogging.get_or_none(
                guild_model_id=guild_model._id
            )
            if not guild_logging:
                return Result.Ok(None)

            if flag == "member_join" and not guild_logging.member_join_enabled:
                return Result.Ok(None)
            if flag == "member_leave" and not guild_logging.member_leave_enabled:
                return Result.Ok(None)
            if flag == "message_removed" and not guild_logging.message_removed_enabled:
                return Result.Ok(None)
            if flag == "message_edited" and not guild_logging.message_edited_enabled:
                return Result.Ok(None)

            return Result.Ok(guild_logging.logging_channel)
        except Exception as e:
            return Result.Err(
                GuildLoggingServiceError(f"{e}\n{traceback.format_exc()}")
            )
