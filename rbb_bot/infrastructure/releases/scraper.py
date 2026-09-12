import asyncio
import logging
import re
import sys
from logging import Logger

import asyncpraw
import pendulum
from aiohttp import ClientSession
from asyncpraw.models.reddit.subreddit import Subreddit
from asyncpraw.models.reddit.wikipage import WikiPage
from asyncprawcore.exceptions import BadRequest
from bs4 import BeautifulSoup as bs

from rbb_bot.infrastructure.releases.records import PyArtist, PyReleaseType, PyRelease
from rbb_bot.infrastructure.releases.repository import ReleaseRepository
from rbb_bot.application.releases.refresh import RefreshReleases


class Scraper:
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
        self.refresh_lock = asyncio.Lock()
        self.repository = ReleaseRepository()
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.INFO)
            handler = logging.StreamHandler(stream=sys.stdout)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            self.logger.addHandler(handler)

    async def scrape(self, urls=None):
        urls = urls or self.generate_urls()[-1:]
        async with self.refresh_lock:
            self.updating = True
            try:
                await RefreshReleases(self, self.repository).execute(urls)
            except Exception:
                self.logger.exception(
                    "Release refresh failed; stored releases were preserved"
                )
                return False
            finally:
                self.updating = False
        self.logger.info("Update complete")
        return True

    async def read(self, url, saved):
        releases = await self.scrape_url(url)
        return await self.extract_youtube_urls(
            saved, [release.to_dict() for release in releases]
        )

    async def scrape_url(self, url: str) -> list[PyRelease]:
        # For reference
        # table_headers = [
        #     "day",
        #     "time",
        #     "artist",
        #     "album title",
        #     "album type",
        #     "title track",
        #     "streaming",
        # ]
        month = url.split("/")[-2]
        year = int(url.split("/")[-3])
        release_list = list()
        try:
            subreddit: Subreddit = await self.reddit.subreddit("kpop")
            wiki_page: WikiPage = await subreddit.wiki.get_page(
                f"upcoming-releases/{year}/{month}"
            )

            html = wiki_page.content_html
            release_list = self.get_release_list(html, month, year)
        except Exception:
            self.logger.exception("Error retrieving the Reddit release wiki page")
            raise
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
                    except BadRequest:
                        invalid_urls.append(reddit_url)
                        continue
                    youtube_urls.append(post.url)
                cb["reddit_urls"] = [
                    url for url in cb["reddit_urls"] if url not in invalid_urls
                ]
                cb["urls"] = youtube_urls
            return cbs
        except Exception as e:
            self.logger.exception("Error extracting youtube URLs")
            raise

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

    def generate_urls(self) -> list[str]:
        """
        Generate urls to scrape from january 2018 to current month (inclusive)
        """
        current_month = self.month_strings[pendulum.now().month - 1]
        years = [y for y in range(2018, pendulum.now().year + 2)]

        urls = []
        for year in years:
            for month in self.month_strings:
                if year == pendulum.now().year and month == current_month:
                    urls.append(self.reddit_wiki_base.format(year=year, month=month))
                    return urls
                urls.append(self.reddit_wiki_base.format(year=year, month=month))
