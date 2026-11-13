import pytest

from rbb_bot.settings.const import DISCORD_MAX_MESSAGE
from rbb_bot.utils.helpers import large_send

pytestmark = pytest.mark.asyncio


class FakeChannel:
    """Stands in for Discord's own limit: a part it would reject fails the send."""

    def __init__(self):
        self.sent = []

    async def send(self, content):
        assert isinstance(content, str)
        assert 0 < len(content) <= DISCORD_MAX_MESSAGE
        self.sent.append(content)


def long_text(length: int) -> str:
    # Non-repeating enough that a dropped, duplicated or reordered part
    # cannot reassemble into the original.
    return "".join(f"line {i}\n" for i in range(length))[:length]


async def test_message_over_the_limit_arrives_complete_in_several_parts():
    channel = FakeChannel()
    text = long_text(DISCORD_MAX_MESSAGE * 2 + 500)
    await large_send(channel, text)
    assert len(channel.sent) == 3
    assert "".join(channel.sent) == text


async def test_every_part_of_a_long_code_block_is_fenced_within_the_limit():
    channel = FakeChannel()
    text = long_text(DISCORD_MAX_MESSAGE * 2 + 500)
    await large_send(channel, text, code_block=True)
    assert len(channel.sent) > 1
    bodies = []
    for part in channel.sent:
        assert part.startswith("```\n") and part.endswith("\n```")
        bodies.append(part[4:-4])
    assert "".join(bodies) == text


async def test_message_at_the_limit_is_sent_once_unchanged():
    channel = FakeChannel()
    text = long_text(DISCORD_MAX_MESSAGE)
    await large_send(channel, text)
    assert channel.sent == [text]
