import discord
from discord import TextChannel
from tortoise import fields
from tortoise.models import Model

from rbb_bot.models.encrypted import EncryptedModelMixin, EncryptedValue

from rbb_bot.settings.config import get_config
from rbb_bot.utils.mixins import ClientMixin

default_prefix = get_config().default_prefix


class Guild(EncryptedModelMixin, Model, ClientMixin):
    _id = fields.IntField(pk=True)
    id = fields.BigIntField(unique=True)
    prefix_ciphertext = fields.TextField(null=True)
    prefix = EncryptedValue("prefix_ciphertext", default=default_prefix)
    emojis_channel_id = fields.BigIntField(null=True)
    greet_channel_id = fields.BigIntField(null=True)
    emojis_channel_message_ciphertext = fields.TextField(null=True)
    emojis_channel_message = EncryptedValue("emojis_channel_message_ciphertext")
    delete_emoji_messages = fields.BooleanField(default=True)
    custom_roles_enabled = fields.BooleanField(default=False)
    max_custom_roles = fields.IntField(default=2)
    reminders_enabled = fields.BooleanField(default=False)
    departed_at = fields.DatetimeField(null=True, index=True)

    @property
    def guild(self) -> discord.Guild | None:
        return self.client.get_guild(self.id) if self.client else None

    @property
    def emojis_channel(self) -> TextChannel | None:
        if self.emojis_channel_id and self.client:
            return self.client.get_channel(self.emojis_channel_id)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return (
            f"Guild<(id={self.id}, "
            f"{'name=' + self.guild.name + ', ' if self.guild else ''}"
            f"prefix={self.prefix}, "
            f"emojis_channel={self.emojis_channel}, "
            f"custom_roles_enabled={self.custom_roles_enabled}, "
            f"max_custom_roles={self.max_custom_roles}, "
            f"reminders_enabled={self.reminders_enabled})>"
        )


class Greeting(EncryptedModelMixin, Model):
    id = fields.IntField(pk=True)
    guild = fields.ForeignKeyField("models.Guild", related_name="greetings")
    title_ciphertext = fields.TextField(null=True)
    title = EncryptedValue("title_ciphertext", default="Welcome!")
    description_ciphertext = fields.TextField(null=True)
    description = EncryptedValue(
        "description_ciphertext", default="Welcome to the server!"
    )
    show_member_count = fields.BooleanField(default=True)


class JoinResponse(EncryptedModelMixin, Model):
    id = fields.IntField(pk=True)
    event = fields.ForeignKeyField(
        "models.JoinEvent", related_name="join_responses", on_delete=fields.CASCADE
    )
    content_ciphertext = fields.TextField(null=True)
    content = EncryptedValue("content_ciphertext")


class JoinRole(Model):
    id = fields.IntField(pk=True)
    event = fields.ForeignKeyField(
        "models.JoinEvent", related_name="join_roles", on_delete=fields.CASCADE
    )
    role_id = fields.BigIntField(null=False)


class JoinEvent(Model):
    id = fields.IntField(pk=True)
    guild = fields.ForeignKeyField(
        "models.Guild", related_name="join_event", on_delete=fields.CASCADE
    )
    _channel_id = fields.BigIntField(null=True)
    _responses = fields.ManyToManyField(
        "models.JoinResponse", related_name="join_events", on_delete=fields.CASCADE
    )
    _roles = fields.ManyToManyField(
        "models.JoinRole", related_name="join_events", on_delete=fields.CASCADE
    )
