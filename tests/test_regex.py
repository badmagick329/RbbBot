import pytest
from rbb_bot.utils.helpers import emoji_regex, user_regex, channel_regex, role_regex

emoji_regex_params = [
    ("<a:irenelul2:849347940162207764>", ("a", "irenelul2", "849347940162207764")),
    ("<:LudaKeke:593834426962804737>", ("", "LudaKeke", "593834426962804737")),
    ("<a:irenekek2:620961498570817567>", ("a", "irenekek2", "620961498570817567")),
    ("<:KarinaKek1:780263510076686358>", ("", "KarinaKek1", "780263510076686358")),
    ("<:jihyosmirk:854065636376576000>", ("", "jihyosmirk", "854065636376576000")),
    ("<a:elijahfacepalm:807071245988265994>", ("a", "elijahfacepalm", "807071245988265994")),
    ("<:abc:>", None),
    ("<@221379755830804480>", None),
    ("<#770465744390717440>", None),
    ("<221379755830804480>", None),
]


@pytest.mark.parametrize("emoji, expected", emoji_regex_params)
def test_emoji_regex(emoji, expected):
    result = emoji_regex.search(emoji)
    if expected is None:
        assert result is None
    else:
        assert result.groups() == expected


multiple_emoji_regex_params = [
    (
        "<a:irenelul2:849347940162207764> <a:irenelul2:849347940162207764>",
        [
            ("a", "irenelul2", "849347940162207764"),
            ("a", "irenelul2", "849347940162207764"),
        ],
    ),
    (
        "fdsf ds kjl<a:irenelul2:849347940162207764>sdf sdf <a:irenelul2:849347940162207764> sdf",
        [
            ("a", "irenelul2", "849347940162207764"),
            ("a", "irenelul2", "849347940162207764"),
        ],
    ),
    (
        "<:KarinaKek1:780263510076686358> sdfjk <:abc:>",
        [("", "KarinaKek1", "780263510076686358")],
    ),
    (
        "<a:irenelul2:849347940162207764><a:irenelul2:849347940162207764>",
        [
            ("a", "irenelul2", "849347940162207764"),
            ("a", "irenelul2", "849347940162207764"),
        ],
    ),
]


@pytest.mark.parametrize("string, expected", multiple_emoji_regex_params)
def test_multiple_emoji_regex(string, expected):
    result = emoji_regex.findall(string)
    assert result == expected


user_regex_params = [
    ("<@!221379755830804480>", "221379755830804480"),
    ("<@221379755830804480>", "221379755830804480"),
    ("<@!>", None),
    ("<@>", None),
    ("<221379755830804480>", None),
    ("<#770465744390717440>", None),
    ("<a:irenelul2:849347940162207764>", None),
    ("<:LudaKeke:593834426962804737>", None),
    ("<:abc:>", None),
]


@pytest.mark.parametrize("user, expected", user_regex_params)
def test_user_regex(user, expected):
    result = user_regex.search(user)
    if expected is None:
        assert result is None
    else:
        assert result.group(1) == expected


channel_regex_params = [
    ("<#770465744390717440>", "770465744390717440"),
    ("<#>", None),
    ("<@!221379755830804480>", None),
    ("<@221379755830804480>", None),
    ("<@!>", None),
    ("<@>", None),
    ("<221379755830804480>", None),
    ("<a:irenelul2:849347940162207764>", None),
    ("<:LudaKeke:593834426962804737>", None),
    ("<:abc:>", None),
]


@pytest.mark.parametrize("channel, expected", channel_regex_params)
def test_channel_regex(channel, expected):
    result = channel_regex.search(channel)
    if expected is None:
        assert result is None
    else:
        assert result.group(1) == expected


role_regex_params = [
    ("<@&916065526873202698>", "916065526873202698"),
    ("<@&>", None),
    ("<@!221379755830804480>", None),
    ("<@221379755830804480>", None),
]


@pytest.mark.parametrize("role, expected", role_regex_params)
def test_role_regex(role, expected):
    result = role_regex.search(role)
    if expected is None:
        assert result is None
    else:
        assert result.group(1) == expected
