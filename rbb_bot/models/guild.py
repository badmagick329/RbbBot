import discord
from discord import Embed, Member, TextChannel
from tortoise import fields
from tortoise.models import Model

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

    @property
    def guild(self) -> discord.Guild | None:
        return self.client.get_guild(self.id) if self.client else None

    @property
    def emojis_channel(self) -> TextChannel | None:
        if self.emojis_channel_id and self.client:
            return self.client.get_channel(self.emojis_channel_id)

    async def greet_channel(self) -> TextChannel | None:
        if self.greet_channel_id and self.client:
            channel = self.client.get_channel(self.greet_channel_id)
            if channel is None:
                self.greet_channel_id = None
                await self.save()
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
        embed.set_thumbnail(url=member.display_avatar)
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


class JoinResponse(Model):
    id = fields.IntField(pk=True)
    event = fields.ForeignKeyField("models.JoinEvent", related_name="join_responses")
    content = fields.CharField(max_length=DISCORD_MAX_MESSAGE, null=True)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.guild} - {self.content}."


class JoinRole(Model, ClientMixin):
    id = fields.IntField(pk=True)
    event = fields.ForeignKeyField("models.JoinEvent", related_name="join_roles")
    role_id = fields.BigIntField(null=False)

    @property
    def discord_guild(self) -> discord.Guild | None:
        if self.event.guild:
            return self.event.guild.guild

    @property
    def role(self) -> discord.Role | None:
        guild = self.discord_guild
        if guild and self.role_id:
            return guild.get_role(self.role_id)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.guild} - {self.role}."


class JoinEvent(Model, ClientMixin):
    id = fields.IntField(pk=True)
    guild = fields.ForeignKeyField("models.Guild", related_name="join_events")
    _channel_id = fields.BigIntField(null=True)
    _responses = fields.ManyToManyField(
        "models.JoinResponse", related_name="join_events"
    )
    _roles = fields.ManyToManyField("models.JoinRole", related_name="join_events")

    @property
    def channel_id(self) -> int | None:
        return self._channel_id

    @property
    def channel(self) -> TextChannel | None:
        if self._channel_id and self.guild.client:
            return self.guild.client.get_channel(self._channel_id)

    def set_channel(self, channel: TextChannel) -> None:
        self._channel_id = channel.id

    @property
    def responses(self, as_strs=True) -> list[JoinResponse]:
        if as_strs:
            return [response.content for response in self._responses]
        return self._responses

    async def add_response(self, response: str) -> tuple[JoinResponse, bool]:
        """Add response to an event and return a response and a boolean indicating
        whether the response was newly created or not."""
        if self.channel_id is None:
            raise ValueError("JoinEvent channel is not set.")
        if len(response) > DISCORD_MAX_MESSAGE:
            raise ValueError(
                f"Response length exceeds {DISCORD_MAX_MESSAGE} characters."
            )
        saved_response = await JoinResponse.get_or_none(content=response)
        if saved_response is not None:
            return saved_response, False
        join_response = await JoinResponse.create(event=self, content=response)
        self._responses.append(join_response)
        return join_response, True

    async def remove_response(
        self, response_id: int | None, response_content: str | None
    ) -> bool:
        """Remove response by id or content."""
        if response_id is None and response_content is None:
            raise ValueError("Either response_id or response_content must be provided.")
        if response_id is not None:
            response = await JoinResponse.get_or_none(id=response_id)
        else:
            response = await JoinResponse.get_or_none(content=response_content)
        if response is None:
            return False
        await response.delete()
        await self._responses.remove(response)
        return True

    async def remove_responses(self) -> None:
        """Remove all responses from an event."""
        await self._responses.clear()
        orphaned = await JoinResponse.filter(join_events=None)
        await orphaned.delete()

    @property
    def roles(self) -> list[JoinRole]:
        return self._roles

    async def add_role(self, role: discord.Role) -> JoinRole:
        join_role = await JoinRole.create(event=self, role_id=role.id)
        self._roles.append(join_role)
        return join_role

    async def remove_role(self, role: discord.Role) -> bool:
        join_role = await JoinRole.get_or_none(role_id=role.id)
        if join_role is None:
            return False
        await join_role.delete()
        await self._roles.remove(join_role)
        return True

    async def discord_roles(self) -> list[discord.Role] | None:
        guild = self.discord_guild
        if not guild:
            return None
        discord_roles = []
        deleted_roles = []
        for join_role in self.roles:
            role = guild.get_role(join_role.role_id)
            if role is None:
                deleted_roles.append(join_role)
            else:
                discord_roles.append(role)
        if deleted_roles:
            await JoinRole.filter(id__in=[role.id for role in deleted_roles]).delete()
            await self._roles.remove(*deleted_roles)
        return discord_roles

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.guild} - {self.channel} | {len(self.responses)} | {len(self.roles)}."
