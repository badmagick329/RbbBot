"""Auditable lookup, export, and deletion of data linked to a Discord user."""

from datetime import date, datetime

from tortoise import Tortoise
from tortoise.transactions import in_transaction


class UserDataService:
    _tag_opt_out_ids: set[int] = set()

    @staticmethod
    def _model(model_name: str):
        return Tortoise.apps["models"][model_name]

    @classmethod
    async def load_tag_opt_out_cache(cls) -> None:
        cls._tag_opt_out_ids = set(
            await cls._model("DiscordUser")
            .filter(tag_opt_out=True)
            .values_list("id", flat=True)
        )

    @classmethod
    def is_tag_opted_out(cls, user_id: int) -> bool:
        return user_id in cls._tag_opt_out_ids

    @classmethod
    async def set_tag_opt_out(cls, user_id: int, enabled: bool) -> bool:
        user, _ = await cls._model("DiscordUser").get_or_create(id=user_id)
        changed = user.tag_opt_out != enabled
        if changed:
            user.tag_opt_out = enabled
            await user.save(update_fields=["tag_opt_out"])

        if enabled:
            cls._tag_opt_out_ids.add(user_id)
        else:
            cls._tag_opt_out_ids.discard(user_id)
        return changed

    @staticmethod
    def _json_value(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    @classmethod
    async def export(cls, user_id: int) -> dict:
        user = await cls._model("DiscordUser").get_or_none(id=user_id)
        reminders = await cls._model("Reminder").filter(discord_user__id=user_id)
        sources = await cls._model("SourceEntry").filter(user__id=user_id)

        def reminder_data(reminder) -> dict:
            return {
                "id": reminder.id,
                "guild_id": reminder.guild_id,
                "channel_id": reminder.channel_id,
                "text": reminder.text,
                "due_time": cls._json_value(reminder.due_time),
                "created_at": cls._json_value(reminder.created_at),
            }

        def source_data(source) -> dict:
            return {
                "id": source.id,
                "emoji_string": source.emoji_string,
                "emoji_url": source.emoji_url,
                "source_url": source.source_url,
                "event": source.event,
                "source_date": cls._json_value(source.source_date),
                "guild_id": source.guild_id,
                "channel_id": source.channel_id,
                "message_id": source.message_id,
                "jump_url": source.jump_url,
                "conf_message_id": source.conf_message_id,
                "conf_jump_url": source.conf_jump_url,
            }

        return {
            "discord_user": (
                {
                    "id": user.id,
                    "cached_username": user.cached_username,
                    "blacklist": user.blacklist,
                    "tag_opt_out": user.tag_opt_out,
                }
                if user
                else None
            ),
            "reminders": [reminder_data(reminder) for reminder in reminders],
            "source_entries": [source_data(source) for source in sources],
        }

    @classmethod
    async def status(cls, user_id: int) -> dict:
        user = await cls._model("DiscordUser").get_or_none(id=user_id)
        return {
            "exists": user is not None,
            "reminder_count": await cls._model("Reminder")
            .filter(discord_user__id=user_id)
            .count(),
            "source_entry_count": await cls._model("SourceEntry")
            .filter(user__id=user_id)
            .count(),
            "tag_opt_out": user.tag_opt_out if user else False,
            "has_blacklist": bool(user and user.blacklist),
        }

    @classmethod
    async def source_entries_for_deletion(cls, user_id: int) -> list:
        return await cls._model("SourceEntry").filter(user__id=user_id).order_by("id")

    @classmethod
    async def delete_user_data(cls, user_id: int) -> bool:
        """Delete all stored data for a user after remote source posts are removed."""
        async with in_transaction() as connection:
            user = await (
                cls._model("DiscordUser")
                .filter(id=user_id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if user is None:
                return False

            await cls._model("Reminder").filter(discord_user_id=user._id).using_db(
                connection
            ).delete()
            await cls._model("SourceEntry").filter(user_id=user._id).using_db(
                connection
            ).delete()
            await user.delete(using_db=connection)

        cls._tag_opt_out_ids.discard(user_id)
        return True
