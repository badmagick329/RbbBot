import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "rbb_bot"))
from rbb import RbbBot


@pytest.mark.asyncio
async def test_error_logging_omits_command_input_and_attachment_urls():
    secret_argument = "do-not-log-this-command-input"
    attachment_url = "https://example.test/do-not-log-this-attachment"
    ctx = SimpleNamespace(
        guild=SimpleNamespace(id=1234),
        command=SimpleNamespace(qualified_name="tag add"),
        args=(secret_argument,),
        kwargs={"response": secret_argument},
        message=SimpleNamespace(attachments=[SimpleNamespace(url=attachment_url)]),
    )

    logger = Mock()
    error = RuntimeError("expected test error")

    await RbbBot.send_error(SimpleNamespace(logger=logger), ctx=ctx, exc=error)

    message = logger.error.call_args.args[0]
    assert message == "guild_id=1234 command=tag add"
    assert secret_argument not in message
    assert attachment_url not in message
    assert logger.error.call_args.kwargs["exc_info"] is error
