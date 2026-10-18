import asyncio
import json
import re
from datetime import date

import aiohttp
from pydantic import (
    BaseModel,
    Field,
    StrictStr,
    ValidationError,
    conint,
    conlist,
    validator,
)

from rbb_bot.application.wins.latest import RecordedWin, WinsUnavailable
from rbb_bot.settings.config import KpopWinsSettings

PositiveId = conint(strict=True, gt=0)


class ArtistPayload(BaseModel):
    id: PositiveId
    slug: StrictStr = Field(..., max_length=220)
    name: StrictStr = Field(..., min_length=1, max_length=10000)

    @validator("slug")
    def canonical_slug(cls, value):
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", value):
            raise ValueError("Invalid artist slug")
        return value


class SongPayload(BaseModel):
    id: PositiveId
    title: StrictStr = Field(..., min_length=1, max_length=10000)
    artist: ArtistPayload


class ShowPayload(BaseModel):
    name: StrictStr = Field(..., min_length=1, max_length=10000)


class WinPayload(BaseModel):
    id: PositiveId
    date: date
    show: ShowPayload
    song: SongPayload

    @validator("date", pre=True)
    def calendar_date(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Expected calendar date")
        return value


class PagePayload(BaseModel):
    count: conint(strict=True, ge=0)
    next: StrictStr | None = Field(...)
    previous: StrictStr | None = Field(...)
    results: conlist(WinPayload, max_items=100)


class KpopWinsClient:
    """Validate untrusted JSON once; the launcher retains ownership of the session.

    1 MiB allows growth over the largest sampled 83,793-byte page. Bound streamed
    decompressed bytes too, since Content-Length may be absent or compressed.
    """

    MAX_BODY_BYTES = 1024 * 1024

    def __init__(self, session: aiohttp.ClientSession, settings: KpopWinsSettings):
        self.session = session
        self.settings = settings

    async def fetch(self, artist: str | None, cutoff: date) -> tuple[RecordedWin, ...]:
        params = {"ordering": "-date", "date_to": cutoff.isoformat(), "page": "1"}
        if artist is not None:
            params["artist"] = artist
        headers = {"X-Forwarded-Proto": "https", "Accept": "application/json"}
        key = self.settings.internal_key.get_secret_value()
        if key:
            headers["X-KpopWins-Internal-Key"] = key
        try:
            async with self.session.get(
                self.settings.api_base_url + "/wins",
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
                allow_redirects=False,
            ) as response:
                if not 200 <= response.status < 300:
                    raise WinsUnavailable()
                if (
                    response.content_length is not None
                    and response.content_length > self.MAX_BODY_BYTES
                ):
                    raise WinsUnavailable()
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > self.MAX_BODY_BYTES:
                        raise WinsUnavailable()
                page = PagePayload.parse_obj(json.loads(body))
                rows = page.results
                if page.count < len(rows) or (page.count > 0 and not rows):
                    raise WinsUnavailable()
                if any(row.date > cutoff for row in rows):
                    raise WinsUnavailable()
                if rows != sorted(
                    rows, key=lambda row: (-row.date.toordinal(), row.id)
                ):
                    raise WinsUnavailable()
                return tuple(
                    RecordedWin(
                        row.id,
                        row.date,
                        row.show.name,
                        row.song.id,
                        row.song.title,
                        row.song.artist.id,
                        row.song.artist.slug,
                        row.song.artist.name,
                    )
                    for row in rows[:5]
                )
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, ValidationError):
            raise WinsUnavailable() from None
