import asyncio
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest
from pydantic import ValidationError

from rbb_bot.application.wins.latest import (
    InvalidArtist,
    LatestWins,
    WinsUnavailable,
    korean_today,
    normalize_artist,
)
from rbb_bot.infrastructure.wins.client import KpopWinsClient
from rbb_bot.settings.config import KpopWinsSettings


def payload():
    return {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": 1,
                "date": "2026-10-18",
                "show": {"name": "Music Bank"},
                "song": {
                    "id": 2,
                    "title": "Song",
                    "artist": {"id": 3, "slug": "artist", "name": "Artist"},
                },
                "ignored": {"extra": True},
            }
        ],
    }


class Response:
    def __init__(self, data=None, *, body=None, status=200, length=None):
        self.body = (
            json.dumps(payload() if data is None else data).encode()
            if body is None
            else body
        )
        self.status = status
        self.content_length = length
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def iter_chunked(self, size):
        for offset in range(0, len(self.body), size):
            yield self.body[offset : offset + size]


def client(response):
    session = Mock()
    session.get.return_value = response
    return (
        KpopWinsClient(
            session,
            KpopWinsSettings(
                api_base_url="http://kpopwins-api:8000/api/v1",
                internal_key="private-key",
            ),
        ),
        session,
    )


def test_request_contract_and_trusted_dto():
    api, session = client(Response())
    rows = asyncio.run(api.fetch("A&B / 한글", date(2026, 10, 18)))
    assert len(rows) == 1
    assert (rows[0].artist_slug, rows[0].song_id, rows[0].date) == (
        "artist",
        2,
        date(2026, 10, 18),
    )
    args, kwargs = session.get.call_args
    assert args == ("http://kpopwins-api:8000/api/v1/wins",)
    assert kwargs["params"] == {
        "ordering": "-date",
        "date_to": "2026-10-18",
        "page": "1",
        "artist": "A&B / 한글",
    }
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"].total == 5
    assert kwargs["headers"]["X-Forwarded-Proto"] == "https"
    assert kwargs["headers"]["X-KpopWins-Internal-Key"] == "private-key"


def test_default_request_and_valid_empty_are_distinct_from_failure():
    api, session = client(
        Response({"count": 0, "next": None, "previous": None, "results": []})
    )
    assert asyncio.run(api.fetch(None, date(2026, 10, 18))) == ()
    assert "artist" not in session.get.call_args.kwargs["params"]


@pytest.mark.parametrize("status", [301, 302, 400, 429, 500, 503])
def test_http_failure_and_redirect(status):
    api, _ = client(Response(status=status))
    with pytest.raises(WinsUnavailable):
        asyncio.run(api.fetch(None, date(2026, 10, 18)))


@pytest.mark.parametrize(
    "body,length",
    [
        (b"not json", None),
        (b"\xff", None),
        (b"x" * (1024 * 1024 + 1), None),
        (b"", 1024 * 1024 + 1),
    ],
    ids=["json", "encoding", "stream-limit", "length-limit"],
)
def test_invalid_or_oversized_body(body, length):
    api, _ = client(Response(body=body, length=length))
    with pytest.raises(WinsUnavailable):
        asyncio.run(api.fetch(None, date(2026, 10, 18)))


@pytest.mark.parametrize(
    "path,value",
    [
        (("count",), True),
        (("results",), None),
        (("results", 0, "id"), "1"),
        (("results", 0, "date"), "2026-02-30"),
        (("results", 0, "date"), 123),
        (("results", 0, "date"), "2026-10-19"),
        (("results", 0, "show", "name"), None),
        (("results", 0, "song", "artist", "slug"), "../../secret"),
        (("results", 0, "song", "artist", "id"), False),
        (("results", 0, "song", "title"), ""),
    ],
)
def test_nested_external_validation(path, value):
    data = payload()
    target = data
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    api, _ = client(Response(data))
    with pytest.raises(WinsUnavailable):
        asyncio.run(api.fetch(None, date(2026, 10, 18)))


@pytest.mark.parametrize(
    "error", [asyncio.TimeoutError(), aiohttp.ClientConnectionError()]
)
def test_transport_failure(error):
    api, session = client(Response())
    session.get.side_effect = error
    with pytest.raises(WinsUnavailable):
        asyncio.run(api.fetch(None, date(2026, 10, 18)))


def test_page_order_and_first_five():
    data = payload()
    data["results"] = [{**data["results"][0], "id": n} for n in range(1, 8)]
    data["count"] = 7
    api, _ = client(Response(data))
    assert [row.id for row in asyncio.run(api.fetch(None, date(2026, 10, 18)))] == [
        1,
        2,
        3,
        4,
        5,
    ]
    data["results"].reverse()
    api, _ = client(Response(data))
    with pytest.raises(WinsUnavailable):
        asyncio.run(api.fetch(None, date(2026, 10, 18)))


def test_cache_expiry_isolation_midnight_capacity_and_failure_recovery():
    async def scenario():
        now, day = [0], [date(2026, 10, 18)]
        source = SimpleNamespace(fetch=AsyncMock(return_value=()))
        use_case = LatestWins(source, clock=lambda: now[0], today=lambda: day[0])
        await use_case.execute(" TWICE ")
        await use_case.execute("TWICE")
        assert source.fetch.await_count == 1
        await use_case.execute("TXT")
        assert source.fetch.await_count == 2
        now[0] = 60
        await use_case.execute("TWICE")
        assert source.fetch.await_count == 3
        day[0] = date(2026, 10, 19)
        await use_case.execute("TWICE")
        source.fetch.assert_awaited_with("TWICE", day[0])
        assert source.fetch.await_count == 4
        for n in range(129):
            await use_case.execute(str(n))
        assert len(use_case._cache) == 128
        before = source.fetch.await_count
        await use_case.execute("0")
        assert source.fetch.await_count == before + 1
        source.fetch.side_effect = WinsUnavailable()
        with pytest.raises(WinsUnavailable):
            await use_case.execute("recover")
        source.fetch.side_effect = None
        await use_case.execute("recover")
        assert ("recover", day[0]) in use_case._cache

    asyncio.run(scenario())


def test_concurrent_cache_misses_share_successful_request():
    async def scenario():
        async def fetch(*args):
            await asyncio.sleep(0)
            return ()

        source = SimpleNamespace(fetch=AsyncMock(side_effect=fetch))
        use_case = LatestWins(source)
        assert (
            await asyncio.gather(*(use_case.execute("TWICE") for _ in range(10)))
            == [()] * 10
        )
        assert source.fetch.await_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("artist", ["", "   ", "a" * 101, "a\nb", "a\x00b"])
def test_artist_validation(artist):
    with pytest.raises(InvalidArtist):
        normalize_artist(artist)


def test_korean_date_rolls_over_before_utc():
    with patch("rbb_bot.application.wins.latest.datetime") as clock:
        clock.now.side_effect = lambda tz: datetime(
            2026, 10, 18, 15, 0, tzinfo=timezone.utc
        ).astimezone(tz)
        assert korean_today() == date(2026, 10, 19)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@api.test/api/v1",
        "ftp://api.test/api/v1",
        "http://api.test/api/v1?secret=x",
        "http://api.test/api/v1#x",
        "http://api.test:bad/api/v1",
        "https://api.test/other",
    ],
)
def test_settings_reject_invalid_api_base(url):
    with pytest.raises(ValidationError):
        KpopWinsSettings(api_base_url=url)


def test_secret_is_redacted_and_invalid_header_rejected():
    settings = KpopWinsSettings(internal_key="private-key")
    assert "private-key" not in repr(settings)
    assert "private-key" not in settings.json()
    with pytest.raises(ValidationError):
        KpopWinsSettings(internal_key="private\r\nkey")
