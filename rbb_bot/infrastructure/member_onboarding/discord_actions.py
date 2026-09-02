import random
from logging import Logger

from discord import Member

from rbb_bot.domain.member_onboarding import GreetingTemplate
from rbb_bot.models import Greeting, Guild, JoinEvent
from rbb_bot.services.auto_role_service import AutoRoleService
from rbb_bot.views.member_onboarding import create_greeting_embed


class DiscordMemberOnboardingActions:
    """Fulfil onboarding actions through Discord and the current ORM models."""

    def __init__(self, member: Member, logger: Logger) -> None:
        self.member = member
        self.logger = logger
        self._guild_loaded = False
        self._guild: Guild | None = None

    async def _stored_guild(self) -> Guild | None:
        if not self._guild_loaded:
            self._guild = await Guild.get_or_none(id=self.member.guild.id)
            self._guild_loaded = True
        return self._guild

    async def send_greeting(self) -> None:
        guild = await self._stored_guild()
        if guild is None or not guild.greet_channel_id:
            return

        greeting = await Greeting.get_or_none(guild=guild)
        if greeting is None:
            return

        channel = await guild.greet_channel()
        if channel is not None:
            template = GreetingTemplate(
                title=greeting.title,
                description=greeting.description,
                show_member_count=greeting.show_member_count,
            )
            await channel.send(embed=create_greeting_embed(template, self.member))

    async def send_join_response(self) -> None:
        guild = await self._stored_guild()
        if guild is None:
            return

        join_event = await JoinEvent.get_or_none(guild=guild)
        if join_event is None or join_event.channel is None:
            return

        messages = await join_event.responses_as_str()
        if messages:
            await join_event.channel.send(random.choice(messages))

    async def apply_auto_roles(self) -> None:
        guild = await self._stored_guild()
        if guild is None:
            return

        result = await AutoRoleService.list_with_cleanup(self.member.guild.id)
        if result.is_err:
            raise result.unwrap_err()

        roles = result.unwrap()
        if not roles:
            return

        bot_member = self.member.guild.me
        if bot_member is None:
            self.logger.error(
                "Bot member unavailable for auto roles in guild %s",
                self.member.guild.id,
            )
            return

        if not bot_member.guild_permissions.manage_roles:
            self.logger.warning(
                "Missing `Manage Roles` permission in %s for auto roles",
                self.member.guild.name,
            )
            return

        await self.member.add_roles(*roles)
