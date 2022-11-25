import asyncio
import json
import logging
import re
from copy import deepcopy
from logging import Logger
from pathlib import Path

import aiohttp
import asyncpraw
import pendulum
from aiohttp import ClientSession
from bs4 import BeautifulSoup as bs
from pydantic import BaseModel
from tortoise import Tortoise

from rbb_bot.settings.config import get_creds, get_config


class PyArtist(BaseModel):
    id: int | None
    name: str

    class Config:
        orm_mode = True


class PyReleaseType(BaseModel):
    id: int | None
    name: str

    class Config:
        orm_mode = True


class PyRelease(BaseModel):
    """
    Datetimes are saved in KST
    """

    id: int | None
    release_date: pendulum.Date
    release_time: pendulum.DateTime | None
    artist: PyArtist
    title: str
    album_title: str
    release_type: PyReleaseType
    reddit_urls: list[str]
    urls: list[str] | None

    class Config:
        orm_mode = True

    def __init__(self, **data):
        super().__init__(**data)
        self.format_dates()

    def format_dates(self) -> "PyRelease":
        self.release_date = pendulum.parse(str(self.release_date)).date()
        if self.release_time:
            self.release_time = pendulum.instance(self.release_time).in_timezone(
                "Asia/Seoul"
            )
        return self

    def to_dict(self) -> dict:
        d = self.dict()
        d["id"] = int(d["id"]) if d["id"] else None
        d["artist_id"] = d["artist"]["id"]
        d["artist"] = d["artist"]["name"]
        d["release_type_id"] = d["release_type"]["id"]
        d["release_type"] = d["release_type"]["name"]
        d["release_date"] = str(d["release_date"])
        if d["release_time"]:
            d["release_time"] = str(d["release_time"])
        return d

    @staticmethod
    def from_dict(d: dict) -> "PyRelease":
        d["artist"] = PyArtist(
            id=d["artist_id"] if "artist_id" in d else None, name=d["artist"]
        )
        d["release_type"] = PyReleaseType(
            id=d["release_type_id"] if "release_type_id" in d else None,
            name=d["release_type"],
        )
        d["release_date"] = pendulum.parse(d["release_date"]).date()
        if d["release_time"]:
            d["release_time"] = pendulum.parse(d["release_time"])
        return PyRelease(**d)


class Scraper:
    JSON_FILE = (
        Path(__file__).parent.parent
        / "data"
        / "import_data"
        / "reddit_scraper_output.json"
    )
    reddit_wiki_base = (
        "https://www.reddit.com/r/kpop/wiki/upcoming-releases/{year}/{month}/"
    )
    month_strings = [
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]

    def __init__(
        self,
        web_client: ClientSession,
        headers: dict,
        logger: Logger = None,
        creds: dict = None,
        reddit: asyncpraw.Reddit = None,
    ):
        assert creds or reddit, "Must provide either creds or reddit instance"
        if reddit:
            self.reddit = reddit
        else:
            self.reddit = asyncpraw.Reddit(
                client_id=creds.reddit_id,
                client_secret=creds.reddit_secret,
                user_agent=creds.reddit_agent,
            )
        self.web_client = web_client
        self.headers = headers
        self.updating = False
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(LOG_LEVEL)
            handler = logging.StreamHandler(stream=sys.stdout)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            self.logger.addHandler(handler)

    async def scrape(self, urls: list[str]=None, from_json: bool = False):
        if not urls:
            urls = self.generate_urls()[-1:]

        if from_json:
            saved_cbs = self.cbs_from_json(self.JSON_FILE)
        else:
            saved_cbs = await self.cbs_from_db()

        for i, url in enumerate(urls):
            try:
                self.logger.info(f"Scraping {url}")
                cbs = await self.scrape_url(url)
                new_cbs = [cb.to_dict() for cb in cbs]
                new_cbs = await self.extract_youtube_urls(saved_cbs, new_cbs)
            except Exception as e:
                self.logger.error(f"Error scraping {url}\n{e}")
                return
            try:
                self.logger.debug(
                    f"Merging {len(new_cbs)} releases with {len(saved_cbs)} releases"
                )
                merged_cbs = self.merge_cbs(saved_cbs, new_cbs)
            except Exception as e:
                self.logger.error(f"Error merging\n{e}")
                return
        self.updating = True
        try:
            if from_json:
                self.save_to_json(merged_cbs, self.JSON_FILE)
            else:
                await self.save_to_db(merged_cbs)
        except Exception as e:
            self.logger.error(f"Error saving {e}", exc_info=e, stack_info=True)
            return
        self.updating = False
        self.logger.info("Update complete")

    async def scrape_url(self, url: str) -> list[PyRelease]:
        # For reference
        table_headers = [
            "day",
            "time",
            "artist",
            "album title",
            "album type",
            "title track",
            "streaming",
        ]
        month = url.split("/")[-2]
        year = int(url.split("/")[-3])
        release_list = list()
        async with self.web_client.get(url, headers=self.headers) as response:
            if response.status == 200:
                html = await response.text()
                release_list = self.get_release_list(html, month, year)
        return release_list

    @staticmethod
    def get_release_list(html: str, month: str, year: str) -> list[PyRelease]:
        release_list = list()
        soup = bs(html, "lxml")
        rows = soup.select("table")[0].select("tbody")[0].select("tr")
        release_date = None
        day = ""
        for row in rows:
            release_time = None
            artist = None
            album_title = None
            release_type = None
            title = ""
            reddit_urls = list()

            for i, cell in enumerate(row.select("td")):
                if i == 0:
                    if not cell.text:
                        continue
                    day = cell.text
                    day = day[:-2]
                    release_date = pendulum.from_format(
                        f"{day} {month.title()} {year}",
                        "DD MMMM YYYY",
                        tz="Asia/Seoul",
                    )
                    continue
                if i == 1:
                    if not re.search(r"\d{1,2}[:.]\d{2}", cell.text):
                        release_time = None
                        continue
                    time = cell.text
                    split_by = ":" if ":" in time else "."
                    release_time = release_date.set(
                        hour=int(time.split(split_by)[0]),
                        minute=int(time.split(split_by)[1]),
                    )
                    continue
                if i == 2:
                    artist = PyArtist(name=cell.text)
                    continue
                if i == 3:
                    album_title = cell.text
                    continue
                if i == 4:
                    release_type = PyReleaseType(name=cell.text)
                    continue
                if i == 5:
                    children = cell.contents
                    title = cell.text
                    for child in children:
                        if child.name == "a":
                            reddit_urls.append(child["href"])
                    continue
            release = PyRelease(
                release_date=release_date,
                release_time=release_time,
                artist=artist,
                title=title,
                album_title=album_title,
                release_type=release_type,
                reddit_urls=reddit_urls,
                urls=None,
            )
            release_list.append(release)
        return release_list

    async def extract_youtube_urls(
        self, saved_cbs: list[dict], cbs: list[dict]
    ) -> list[dict]:
        """
        Get youtube urls from reddit posts. Return altered cbs
        """

        def url_to_id(url: str):
            if "comments" in url:
                return url.split("comments/")[-1].split("/")[0]
            else:
                return url.replace("/", "")

        def in_saved_cbs(cb: dict) -> dict | None:
            for saved_cb in saved_cbs:
                if self.cb_dicts_eq(cb, saved_cb, match_urls=False):
                    return saved_cb

        try:
            for i, cb in enumerate(cbs):
                if cb["urls"] is not None and not (
                    len(cb["urls"]) == 0 and len(cb["reddit_urls"]) > 0
                ):
                    continue
                saved_cb = in_saved_cbs(cb)
                if saved_cb and saved_cb["urls"]:
                    cb["urls"] = saved_cb["urls"]
                    continue

                youtube_urls = list()
                invalid_urls = list()
                for reddit_url in cb["reddit_urls"]:
                    if "youtube" in reddit_url or "youtu.be" in reddit_url:
                        youtube_urls.append(reddit_url)
                        continue
                    post_id = url_to_id(reddit_url)
                    try:
                        post = await self.reddit.submission(post_id)
                    except NotFound:
                        invalid_urls.append(reddit_url)
                        continue
                    youtube_urls.append(post.url)
                cb["reddit_urls"] = [
                    url for url in cb["reddit_urls"] if url not in invalid_urls
                ]
                cb["urls"] = youtube_urls
            return cbs
        except Exception as e:
            self.logger.error(
                f"Error extracting youtube urls: {e}", exc_info=e, stack_info=True
            )

    def merge_cbs(self, old_cbs: list[dict], new_cbs: list[dict]) -> list[dict]:
        """
        Merge new_cbs into old_cbs. All old_cb dates that are in new_cbs are replaced with new_cbs
        """
        old_cbs = deepcopy(old_cbs)
        remove_dates = list(set([cb["release_date"] for cb in new_cbs]))
        merged_cbs = [c for c in old_cbs if c["release_date"] not in remove_dates]
        merged_cbs.extend(new_cbs)
        return merged_cbs

    @staticmethod
    def cb_dicts_eq(cb1: dict, cb2: dict, match_urls=True) -> bool:
        """
        Check if two cbs are equal
        """
        return (
            cb1["release_date"] == cb2["release_date"]
            and cb1["release_time"] == cb2["release_time"]
            and cb1["artist"] == cb2["artist"]
            and cb1["title"] == cb2["title"]
            and cb1["album_title"] == cb2["album_title"]
            and cb1["release_type"] == cb2["release_type"]
            and cb1["reddit_urls"] == cb2["reddit_urls"]
            and (cb1["urls"] == cb2["urls"] if match_urls else True)
        )

    @staticmethod
    def cbs_from_json(json_file):
        with open(json_file, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_to_json(cbs: list[dict], json_file):
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(cbs, f, indent=4, ensure_ascii=False)

    @staticmethod
    async def cbs_from_db(recent: bool = True):
        """
        Get the cbs from the database

        Parameters
        ----------
        recent: bool
            If True, only get the cbs from the last 2 months
        """
        if recent:
            start_date = pendulum.now().subtract(months=2).date()
            releases = await Release.filter(
                release_date__gte=start_date
            ).prefetch_related("release_type", "artist")
        else:
            releases = await Release.all().prefetch_related("release_type", "artist")
        return [
            PyRelease.from_orm(release).format_dates().to_dict() for release in releases
        ]

    async def save_to_db(self, cbs: list[dict]):
        """
        Save the cbs to the database
        """
        update_releases = list()
        create_releases = list()
        BATCH = 500

        remove_dates = [cb["release_date"] for cb in cbs if cb["id"] is None]
        remove_dates = list(set(remove_dates))
        await Release.filter(release_date__in=remove_dates).delete()

        artist_names = list(set([cb["artist"] for cb in cbs]))
        release_types_names = list(set([cb["release_type"] for cb in cbs]))
        saved_artists = await Artist.filter(name__in=artist_names)
        saved_release_types = await ReleaseType.filter(name__in=release_types_names)
        artist_names_map = {artist.name: artist for artist in saved_artists}
        release_types_names_map = {
            release_type.name: release_type for release_type in saved_release_types
        }

        for i, cb in enumerate(cbs):
            if cb["id"] is None:
                if cb["artist"] not in artist_names_map:
                    artist = Artist(name=cb["artist"])
                    artist_names_map[cb["artist"]] = artist
                    await artist.save()
                else:
                    artist = artist_names_map[cb["artist"]]
                if cb["release_type"] not in release_types_names_map:
                    release_type = ReleaseType(name=cb["release_type"])
                    release_types_names_map[cb["release_type"]] = release_type
                    await release_type.save()
                else:
                    release_type = release_types_names_map[cb["release_type"]]
                release = Release(
                    artist=artist,
                    album_title=cb["album_title"],
                    title=cb["title"],
                    release_date=cb["release_date"],
                    release_time=pendulum.parse(cb["release_time"])
                    if cb["release_time"]
                    else None,
                    release_type=release_type,
                    urls=cb["urls"],
                    reddit_urls=cb["reddit_urls"],
                )
                create_releases.append(release)
                if len(create_releases) == BATCH:
                    await Release.bulk_create(create_releases)
                    create_releases = list()
            else:
                release = await Release.get(id=cb["id"])
                release.release_time = (
                    pendulum.parse(cb["release_time"]) if cb["release_time"] else None
                )
                release.reddit_urls = cb["reddit_urls"]
                release.urls = cb["urls"] if cb["urls"] else release.urls
                update_releases.append(release)
                if len(update_releases) == BATCH:
                    await Release.bulk_update(
                        update_releases, fields=["release_time", "reddit_urls", "urls"]
                    )
                    update_releases = list()

        if len(create_releases) > 0:
            await Release.bulk_create(create_releases)

        if len(update_releases) > 0:
            await Release.bulk_update(
                update_releases, fields=["release_time", "reddit_urls", "urls"]
            )

    def generate_urls(self) -> list[str]:
        """
        Generate urls to scrape from january 2018 to current month (inclusive)
        """
        next_month = self.month_strings[pendulum.now().month]
        years = [y for y in range(2018, pendulum.now().year + 2)]

        urls = []
        for year in years:
            for month in self.month_strings:
                if year == pendulum.now().year and month == next_month:
                    return urls
                urls.append(self.reddit_wiki_base.format(year=year, month=month))


async def init():
    await Tortoise.init(
        db_url=get_creds().db_url, modules={"models": ["rbb_bot.models"]}
    )
    await Tortoise.generate_schemas(safe=True)


async def simple_update():
    async with aiohttp.ClientSession() as web_client:
        headers = get_config().headers
        scraper = Scraper(
            web_client=web_client,
            headers=headers,
            creds=get_creds(),
        )
        await scraper.scrape(from_json=False)
    await scraper.reddit.close()


async def main():
    await init()
    await simple_update()


if __name__ == "__main__":
    from rbb_bot.models import Release, ReleaseType, Artist

    asyncio.run(main())
else:
    from models import Release, ReleaseType, Artist
