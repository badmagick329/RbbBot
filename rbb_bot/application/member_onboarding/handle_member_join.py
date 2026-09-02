from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Protocol


class MemberJoinAction(str, Enum):
    GREETING = "greeting"
    JOIN_RESPONSE = "join_response"
    AUTO_ROLES = "auto_roles"


class MemberJoinActions(Protocol):
    async def send_greeting(self) -> None:
        ...

    async def send_join_response(self) -> None:
        ...

    async def apply_auto_roles(self) -> None:
        ...


@dataclass(frozen=True)
class MemberJoinFailure:
    action: MemberJoinAction
    error: Exception
    traceback: TracebackType | None


class HandleMemberJoin:
    """Run independent onboarding actions without one failure blocking the rest."""

    def __init__(self, actions: MemberJoinActions) -> None:
        self.actions = actions

    async def execute(self) -> tuple[MemberJoinFailure, ...]:
        failures = []
        operations = (
            (MemberJoinAction.GREETING, self.actions.send_greeting),
            (MemberJoinAction.JOIN_RESPONSE, self.actions.send_join_response),
            (MemberJoinAction.AUTO_ROLES, self.actions.apply_auto_roles),
        )

        for action, operation in operations:
            try:
                await operation()
            except Exception as error:
                failures.append(MemberJoinFailure(action, error, error.__traceback__))

        return tuple(failures)
