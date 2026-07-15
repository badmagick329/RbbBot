import pytest
from rbb_bot.utils.help_command import EmbedHelpCommand

parse_params = [
    (
        """Add an emote to the server

Parameters
----------
name: str
    The name of the emote
url: Optional[str]
    The url of the image or gif to add as an emote. Attachment used if not provided.""",
        """Add an emote to the server

**Parameters**
**name**
The name of the emote
**url**
The url of the image or gif to add as an emote. Attachment used if not provided.""",
    )
]


@pytest.mark.parametrize("docstring, expected", parse_params)
def test_parse_help_text(docstring, expected):
    result = EmbedHelpCommand.parse_help_text(docstring)
    assert result == expected
