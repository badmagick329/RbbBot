from dataclasses import dataclass
from typing import Protocol

from rbb_bot.domain.member_onboarding import GreetingTemplate


@dataclass(frozen=True)
class GreetingSettings:
    channel_id: int | None
    template: GreetingTemplate | None


@dataclass(frozen=True)
class WelcomeMessage:
    id: int
    content: str


@dataclass(frozen=True)
class WelcomeSettings:
    channel_id: int | None
    messages: tuple[WelcomeMessage, ...]


@dataclass(frozen=True)
class RoleInfo:
    id: int
    name: str
    assignable: bool


@dataclass(frozen=True)
class MemberInfo:
    id: int
    bot: bool
    role_ids: frozenset[int]


class OnboardingRepository(Protocol):
    async def greeting(self, guild_id: int) -> GreetingSettings:
        ...

    async def set_greeting_channel(self, guild_id: int, channel_id: int | None) -> None:
        ...

    async def update_greeting(
        self,
        guild_id: int,
        title: str | None,
        description: str | None,
        show_count: bool,
    ) -> GreetingSettings:
        ...

    async def welcome(self, guild_id: int) -> WelcomeSettings:
        ...

    async def set_welcome_channel(self, guild_id: int, channel_id: int | None) -> None:
        ...

    async def add_messages(self, guild_id: int, messages: tuple[str, ...]) -> int:
        ...

    async def remove_messages(self, guild_id: int, ids: tuple[int, ...]) -> int:
        ...

    async def role_ids(self, guild_id: int) -> tuple[int, ...]:
        ...

    async def add_role(self, guild_id: int, role_id: int) -> bool:
        ...

    async def remove_roles(self, guild_id: int, ids: tuple[int, ...]) -> int:
        ...


class OnboardingDiscord(Protocol):
    async def channel_exists(self, guild_id: int, channel_id: int) -> bool:
        ...

    async def roles(self, guild_id: int, ids: tuple[int, ...]) -> tuple[RoleInfo, ...]:
        ...

    async def apply_roles(
        self, guild_id: int, member_id: int, role_ids: tuple[int, ...]
    ) -> None:
        ...

    async def send_greeting(self, channel_id: int, template: GreetingTemplate) -> None:
        ...

    async def send_welcome(self, channel_id: int, content: str) -> None:
        ...


class WelcomeUrlSource(Protocol):
    async def urls(
        self, guild_id: int, channel_id: int, attachments: bool
    ) -> tuple[str, ...]:
        ...
