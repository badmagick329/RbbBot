"""Fetch untrusted URLs without access to the bot's private network or shared session credentials."""

import ipaddress
import json
import socket

import aiohttp
from aiohttp.resolver import ThreadedResolver
from aiohttp.helpers import is_ip_address
from yarl import URL

from rbb_bot.utils.exceptions import NotOk

MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5


class UnsafeDownload(ValueError):
    pass


def public_address(host):
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise UnsafeDownload("Invalid destination address") from error
    if not address.is_global or address.is_multicast:
        raise UnsafeDownload("Only public internet destinations are allowed")
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            public_address(str(address.ipv4_mapped))
        elif address not in ipaddress.ip_network("2000::/3"):
            raise UnsafeDownload("Special-use IPv6 destinations are not allowed")
        if address.sixtofour is not None or address.teredo is not None:
            raise UnsafeDownload("IPv6 transition addresses are not allowed")
    elif address in ipaddress.ip_network("192.0.0.0/24"):
        raise UnsafeDownload("Special-use destinations are not allowed")


def public_url(value):
    try:
        url = URL(value)
        host = url.raw_host
        if (
            url.scheme not in {"http", "https"}
            or not host
            or url.user is not None
            or "%" in host
        ):
            raise UnsafeDownload("Use a public HTTP or HTTPS URL without credentials")
        # Validate ports now, before a request is sent.
        url.port
        try:
            ipaddress.ip_address(host)
        except ValueError:
            # aiohttp accepts some noncanonical literals and skips DNS for them.
            if is_ip_address(host):
                raise UnsafeDownload("Noncanonical IP addresses are not allowed")
        else:
            public_address(host)
        return url
    except ValueError as error:
        raise UnsafeDownload(str(error)) from error


class PublicResolver(ThreadedResolver):
    """Check the exact addresses handed to the connector, avoiding a second DNS lookup after validation."""

    async def resolve(self, host, port=0, family=socket.AF_INET):
        records = await super().resolve(host, port, family)
        for record in records:
            public_address(record["host"])
        return records


async def read_bounded(response, max_bytes):
    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
        raise UnsafeDownload("Compressed HTTP responses are not supported")
    if response.content_length is not None and response.content_length > max_bytes:
        raise UnsafeDownload("Download exceeds the size limit")
    body = bytearray()
    async for chunk in response.content.iter_chunked(64 * 1024):
        if len(body) + len(chunk) > max_bytes:
            raise UnsafeDownload("Download exceeds the size limit")
        body.extend(chunk)
    return bytes(body)


async def download(url, timeout=5.0, as_text=False, as_json=False):
    target = public_url(url)
    resolver = PublicResolver()
    try:
        connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=timeout),
            cookie_jar=aiohttp.DummyCookieJar(),
            trust_env=False,
            auto_decompress=False,
            headers={"Accept-Encoding": "identity"},
        ) as session:
            for redirects in range(MAX_REDIRECTS + 1):
                async with session.get(target, allow_redirects=False) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location or redirects == MAX_REDIRECTS:
                            raise UnsafeDownload("Invalid or excessive redirects")
                        target = public_url(target.join(URL(location)))
                        continue
                    if response.status != 200:
                        raise NotOk(response.status)
                    body = await read_bounded(response, MAX_DOWNLOAD_BYTES)
                    if as_json:
                        return json.loads(body)
                    if as_text:
                        return body.decode(
                            response.charset or "utf-8", errors="replace"
                        )
                    return body
    finally:
        await resolver.close()
