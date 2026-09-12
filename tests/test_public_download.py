import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from rbb_bot.infrastructure.http.public_download import (
    PublicResolver,
    UnsafeDownload,
    download,
    public_url,
    read_bounded,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://127.000.000.001/x",
        "http://192.168.001.001/x",
        "http://10.1.2.3/x",
        "http://169.254.169.254/x",
        "http://[::1]/",
        "http://[64:ff9b::7f00:1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[fe80::1]/",
        "http://224.0.0.1/",
        "http://192.0.0.8/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "https://user:password@example.com/",
    ],
)
def test_rejects_nonpublic_literal_destinations(url):
    with pytest.raises(UnsafeDownload):
        public_url(url)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "addresses", [["127.0.0.1"], ["93.184.216.34", "10.0.0.1"], ["::1"]]
)
async def test_connector_resolver_rejects_private_dns_answers(addresses):
    with patch(
        "aiohttp.resolver.ThreadedResolver.resolve",
        new=AsyncMock(return_value=[{"host": ip} for ip in addresses]),
    ):
        resolver = PublicResolver()
        try:
            with pytest.raises(UnsafeDownload):
                await resolver.resolve("example.com", 443, socket.AF_UNSPEC)
        finally:
            await resolver.close()


@pytest.mark.asyncio
async def test_resolver_passes_only_checked_addresses_to_connector():
    records = [{"host": "93.184.216.34", "port": 443}]
    with patch(
        "aiohttp.resolver.ThreadedResolver.resolve", new=AsyncMock(return_value=records)
    ) as resolve:
        resolver = PublicResolver()
        try:
            assert await resolver.resolve("example.com", 443) == records
            resolve.assert_awaited_once()
        finally:
            await resolver.close()


class Response:
    def __init__(self, body=b"image", status=200, headers=None, length=None):
        self.body, self.status, self.headers = body, status, headers or {}
        self.content_length, self.charset = length, "utf-8"
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def iter_chunked(self, size):
        class Chunks:
            def __init__(self, body):
                self.chunks = iter(
                    body[offset : offset + 2] for offset in range(0, len(body), 2)
                )

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self.chunks)
                except StopIteration:
                    raise StopAsyncIteration

        return Chunks(self.body)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        Response(b"123456"),
        Response(length=6),
        Response(headers={"Content-Encoding": "gzip"}),
    ],
)
async def test_download_size_and_encoding_limits(response):
    with pytest.raises(UnsafeDownload):
        await read_bounded(response, 5)


@pytest.mark.asyncio
async def test_redirect_to_private_host_is_rejected_before_request():
    session = Mock()
    session.get.return_value = Response(
        status=302, headers={"Location": "http://127.0.0.1/private"}
    )
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    with patch("aiohttp.ClientSession", return_value=session), patch(
        "aiohttp.TCPConnector"
    ):
        with pytest.raises(UnsafeDownload):
            await download("https://example.com/image")
    assert session.get.call_count == 1
    assert session.get.call_args.kwargs == {"allow_redirects": False}


@pytest.mark.asyncio
async def test_public_relative_redirect_and_successful_bounded_download():
    session = Mock()
    session.get.side_effect = [
        Response(status=302, headers={"Location": "/image"}),
        Response(b"image"),
    ]
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    with patch("aiohttp.ClientSession", return_value=session) as create, patch(
        "aiohttp.TCPConnector"
    ) as connector:
        assert await download("https://example.com/start") == b"image"
    assert str(session.get.call_args.args[0]) == "https://example.com/image"
    assert connector.call_args.kwargs["use_dns_cache"] is False
    assert isinstance(connector.call_args.kwargs["resolver"], PublicResolver)
    assert create.call_args.kwargs["trust_env"] is False
    assert create.call_args.kwargs["auto_decompress"] is False


@pytest.mark.asyncio
async def test_dns_change_is_checked_again_on_next_connection():
    answers = [[{"host": "93.184.216.34"}], [{"host": "127.0.0.1"}]]
    with patch(
        "aiohttp.resolver.ThreadedResolver.resolve", new=AsyncMock(side_effect=answers)
    ):
        resolver = PublicResolver()
        try:
            assert await resolver.resolve("example.com", 443) == answers[0]
            with pytest.raises(UnsafeDownload):
                await resolver.resolve("example.com", 443)
        finally:
            await resolver.close()
