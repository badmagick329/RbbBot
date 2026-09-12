import re

import discord

from rbb_bot.application.member_onboarding.contracts import RoleInfo, MemberInfo
from rbb_bot.domain.member_onboarding.configuration import OnboardingInputError
from rbb_bot.views.member_onboarding import create_greeting_embed


class DiscordOnboarding:
    """Resolve cache misses through Discord without rewriting stored configuration."""

    def __init__(self, bot, member=None):
        self.bot = bot
        self.member = member

    async def _channel(self, channel_id):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(channel_id)
        return channel

    async def channel_exists(self, guild_id: int, channel_id: int) -> bool:
        try:
            channel = await self._channel(channel_id)
        except discord.NotFound:
            return False
        return isinstance(channel, discord.TextChannel) and channel.guild.id == guild_id

    async def can_send_messages(self, guild_id: int, channel_id: int) -> bool:
        channel = await self._channel(channel_id)
        permissions = channel.permissions_for(self.bot.get_guild(guild_id).me)
        return permissions.view_channel and permissions.send_messages

    async def send_greeting(self, channel_id, template):
        channel = await self._channel(channel_id)
        await channel.send(embed=create_greeting_embed(template, self.member))

    async def send_welcome(self, channel_id, content):
        channel = await self._channel(channel_id)
        await channel.send(content)

    async def roles(self, guild_id, ids):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise OnboardingInputError("Guild is unavailable")
        roles = {role.id: role for role in guild.roles}
        if any(role_id not in roles for role_id in ids):
            roles = {role.id: role for role in await guild.fetch_roles()}
        bot_member = guild.me
        can_manage = (
            bot_member is not None and bot_member.guild_permissions.manage_roles
        )
        return tuple(
            RoleInfo(
                role.id,
                role.name,
                bool(
                    can_manage
                    and not role.is_default()
                    and not role.managed
                    and role < bot_member.top_role
                ),
            )
            for role_id in ids
            if (role := roles.get(role_id)) is not None
        )

    async def apply_roles(self, guild_id, member_id, role_ids):
        guild = self.bot.get_guild(guild_id)
        if guild.me is None or not guild.me.guild_permissions.manage_roles:
            raise OnboardingInputError(
                "I need the Manage Roles permission to apply auto roles"
            )
        member = (
            self.member
            if self.member is not None and self.member.id == member_id
            else guild.get_member(member_id)
        )
        if member is None:
            member = await guild.fetch_member(member_id)
        # Discord object IDs let the API report a role deleted after resolution.
        await member.add_roles(
            *(discord.Object(id=role_id) for role_id in role_ids),
            reason="Auto role assignment",
        )


class DiscordWelcomeUrls:
    def __init__(self, bot):
        self.discord = DiscordOnboarding(bot)

    async def urls(self, guild_id, channel_id, attachments):
        channel = await self.discord._channel(channel_id)
        if channel.guild.id != guild_id:
            raise OnboardingInputError("The source channel must belong to this server")
        urls = []
        async for message in channel.history(limit=None):
            urls.extend(re.findall(r"https?://\S+\.\S+", message.content))
            if attachments:
                urls.extend(attachment.url for attachment in message.attachments)
        return tuple(urls)


def member_info(member) -> MemberInfo:
    return MemberInfo(
        member.id, member.bot, frozenset(role.id for role in member.roles)
    )
