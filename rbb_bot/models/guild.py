from discord import Embed, Member, TextChannel
from tortoise import Model, fields

from rbb_bot.settings.config import get_config
from rbb_bot.settings.const import (DISCORD_MAX_MESSAGE, EMBED_MAX_DESC,
                                    EMBED_MAX_TITLE)
from rbb_bot.utils.mixins import ClientMixin

default_prefix = get_config().default_prefix


class Guild(Model, ClientMixin):
    _id = fields.IntField(pk=True)
    id = fields.BigIntField(unique=True)
    prefix = fields.CharField(max_length=10, default=default_prefix)
    emojis_channel_id = fields.BigIntField(null=True)
    greet_channel_id = fields.BigIntField(null=True)
    emojis_channel_message = fields.CharField(max_length=DISCORD_MAX_MESSAGE, null=True)
    delete_emoji_messages = fields.BooleanField(default=True)
    custom_roles_enabled = fields.BooleanField(default=False)
    max_custom_roles = fields.IntField(default=2)
    reminders_enabled = fields.BooleanField(default=False)

    MAX_PREFIX = 10

    @property
    def guild(self):
        return self.client.get_guild(self.id) if self.client else None

    @property
    def emojis_channel(self) -> TextChannel | None:
        if self.emojis_channel_id and self.client:
            return self.client.get_channel(self.emojis_channel_id)

    @property
    def greet_channel(self) -> TextChannel | None:
        if self.greet_channel_id and self.client:
            channel = self.client.get_channel(self.greet_channel_id)
            if channel is None:
                self.greet_channel_id = None
                self.save()
            return channel

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return (
            f"{self.guild.name + ' ' if self.guild else ''}({self.id}), "
            f"Prefix: {self.prefix}, "
            f"Emojis Channel: {self.emojis_channel}, "
            f"Custom Roles Enabled: {self.custom_roles_enabled}, "
            f"Max Custom Roles: {self.max_custom_roles}, "
            f"Reminders Enabled: {self.reminders_enabled} "
        )


class Greeting(Model):
    id = fields.IntField(pk=True)
    guild = fields.ForeignKeyField("models.Guild", related_name="greetings")
    title = fields.CharField(max_length=EMBED_MAX_TITLE, default="Welcome!")
    description = fields.CharField(
        max_length=EMBED_MAX_DESC, default="Welcome to the server!"
    )
    show_member_count = fields.BooleanField(default=True)

    MAX_TITLE = EMBED_MAX_TITLE - 100
    MAX_DESC = EMBED_MAX_DESC - 100

    def create_embed(self, member: Member) -> Embed:
        title = self.title.replace("{username}", member.name)
        description = self.description.replace("{mention}", member.mention)
        embed = Embed(title=title, description=description)
        embed.set_thumbnail(url=member.avatar.url)
        if self.show_member_count:
            embed.set_footer(text=f"Member #{member.guild.member_count}")
        return embed

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return (
            f"{self.guild} - {self.title} | {self.description}."
            f"Show member count: {self.show_member_count}"
        )
