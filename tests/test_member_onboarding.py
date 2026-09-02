import pytest

from rbb_bot.application.member_onboarding import HandleMemberJoin, MemberJoinAction


pytestmark = pytest.mark.asyncio


class RecordingActions:
    def __init__(self, failing_action: MemberJoinAction | None = None) -> None:
        self.failing_action = failing_action
        self.calls = []

    async def _record(self, action: MemberJoinAction) -> None:
        self.calls.append(action)
        if action == self.failing_action:
            raise RuntimeError(f"{action.value} failed")

    async def send_greeting(self) -> None:
        await self._record(MemberJoinAction.GREETING)

    async def send_join_response(self) -> None:
        await self._record(MemberJoinAction.JOIN_RESPONSE)

    async def apply_auto_roles(self) -> None:
        await self._record(MemberJoinAction.AUTO_ROLES)


async def test_member_join_runs_each_action_in_order():
    actions = RecordingActions()

    failures = await HandleMemberJoin(actions).execute()

    assert actions.calls == [
        MemberJoinAction.GREETING,
        MemberJoinAction.JOIN_RESPONSE,
        MemberJoinAction.AUTO_ROLES,
    ]
    assert failures == ()


async def test_member_join_continues_after_an_action_fails():
    actions = RecordingActions(MemberJoinAction.JOIN_RESPONSE)

    failures = await HandleMemberJoin(actions).execute()

    assert actions.calls == [
        MemberJoinAction.GREETING,
        MemberJoinAction.JOIN_RESPONSE,
        MemberJoinAction.AUTO_ROLES,
    ]
    assert len(failures) == 1
    assert failures[0].action == MemberJoinAction.JOIN_RESPONSE
    assert str(failures[0].error) == "join_response failed"
