import asyncio
import logging
import re
import sys
from abc import ABC, abstractmethod
from asyncio import AbstractEventLoop
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Callable

import aiohttp
import asyncpraw
import httpx
from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientConnectorError, TooManyRedirects
from aiohttp.typedefs import LooseCookies
from asyncpraw import reddit
from discord import AllowedMentions, File
from discord.ext.commands import Context
from discord.utils import format_dt
from models import DiskCache
from peony import PeonyClient, exceptions
from peony.data_processing import JSONData, PeonyResponse
from peony.exceptions import DoesNotExist, HTTPNotFound, ProtectedTweet
from settings.config import get_config
from settings.const import (
    DISCORD_MAX_FILE_SIZE,
    DISCORD_MAX_MESSAGE,
    MAX_ATTACHMENTS,
    FilePaths,
)
from utils.exceptions import DownloadedVideoNotFound, FFmpegError, TimeoutError
from utils.ffmpeg import FFmpeg
from utils.helpers import chunker, http_get, subprocess_run, truncate, url_to_filename
from utils.twitter import Tweet, TwitterClient
from yarl import URL


@dataclass
class PostMedia:
    filename: str
    bytes_io: BytesIO


@dataclass
class PostData:
    """
    This class is used to store data about a post

    Attributes
    ----------
    source_url:
        The url of the post
    poster:
        The name of the poster
    created_at:
        The datetime the post was created at. Naive datetime objects, assumed to be UTC
    text:
        The text of the post
    urls:
        A list of urls in the post. When caching, this will only contain urls that
        contain media too large to sent as a discord attachment
    chunked_file_paths:
        A list of file paths to the cached media. This and chunked_media
        should not both contain data
    chunked_media:
        A list of PostMedia objects. This is used in scenarios when the media
        urls are timestamped and one of the media url is too big to be sent as a discord attachment.
        In that case the post will not be cached even if caching is enabled, and the media will be
        sent as a combination of urls and discord attachments
    """

    source_url: str
    poster: str = None
    created_at: datetime = None
    text: str = ""
    urls: list[str] = field(default_factory=list)
    chunked_file_paths: list[list[str]] = field(default_factory=list)
    chunked_media: list[list[PostMedia]] = field(default_factory=list)

    def as_dict(self) -> dict:
        # PostData objects with media are not cached. So they don't need to be serialized
        return {
            "source_url": self.source_url,
            "poster": self.poster,
            "created_at": (
                datetime.strftime(self.created_at, "%Y-%m-%d %H:%M:%S.%f")
                if self.created_at
                else None
            ),
            "text": self.text,
            "urls": self.urls,
            "chunked_file_paths": self.chunked_file_paths,
        }

    @property
    def media_list(self) -> list[PostMedia]:
        return [media for media_list in self.chunked_media for media in media_list]

    @property
    def file_path_list(self) -> list[str]:
        return [
            file_path
            for file_path_list in self.chunked_file_paths
            for file_path in file_path_list
        ]

    @property
    def is_empty(self) -> bool:
        return (
            not self.urls
            and not self.chunked_file_paths
            and not self.chunked_media
            and not self.text
        )

    @staticmethod
    def from_dict(data: dict) -> "PostData":
        return PostData(
            source_url=data["source_url"],
            poster=data["poster"],
            created_at=(
                datetime.strptime(data["created_at"], "%Y-%m-%d %H:%M:%S.%f")
                if data["created_at"]
                else None
            ),
            text=data["text"],
            urls=data["urls"],
            chunked_file_paths=data["chunked_file_paths"],
        )


@dataclass
class SnsMessage:
    """
    Holds formatted data about a post, ready to be sent as a discord message
    """

    content: str
    url_str: str = ""
    file_paths: list[str] = field(default_factory=list)
    media: list[PostMedia] = field(default_factory=list)

    async def send(self, ctx: Context):
        if self.file_paths:
            files = [File(fp) for fp in self.file_paths]
            await ctx.send(
                self.content,
                files=files,
                allowed_mentions=AllowedMentions.none(),
            )
        elif self.media:
            files = [File(fp.bytes_io, fp.filename) for fp in self.media]
            await ctx.send(
                self.content,
                files=files,
                allowed_mentions=AllowedMentions.none(),
            )
        else:
            content = f"{self.content}\n" if self.content else ""
            await ctx.send(
                f"{content}{self.url_str}",
                allowed_mentions=AllowedMentions.none(),
            )


@dataclass
class FetchResult:
    post_data: PostData = None
    exception = None
    error_message: str = None

    def __init__(
        self,
        post_data: PostData = None,
        exception=None,
        error_message: str = None,
    ):
        self.post_data = post_data
        self.exception = exception
        self.error_message = error_message


class Fetcher(ABC):
    url_pat: re.Pattern
    short_pats: list[re.Pattern]

    def __init__(
        self,
        url_pat: re.Pattern,
        short_pats: list[re.Pattern],
        logger=None,
        user_send: Callable = None,
    ):
        self.url_pat = url_pat
        self.short_pats = short_pats
        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.DEBUG)
            handler = logging.StreamHandler(stream=sys.stdout)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            self.logger.addHandler(handler)
        self.user_send = user_send

    @abstractmethod
    async def fetch(self, source_url: str) -> FetchResult:
        """
        Fetch the post data from the source url
        """
        ...

    def url_to_filename(self, url: str) -> str:
        """
        Create a filename for the file at the url
        """
        # TODO:
        # This is coming from helpers. Maybe rename this
        return url_to_filename(url)

    def find_urls(self, text: str) -> list[str]:
        long_matches = self.url_pat.finditer(text)
        found_urls = list()
        for match in long_matches:
            if (url := match.group(0).split("?")[0]) not in found_urls:
                found_urls.append(url)
        for short_pat in self.short_pats:
            short_matches = short_pat.finditer(text)
            for match in short_matches:
                if (url := match.group(0).split("?")[0]) not in found_urls:
                    found_urls.append(url)
        return found_urls

    async def get_download_url(self, url: str) -> str | None:
        """Take either a shortened url or a download url, returns the download url"""
        if re.match(self.url_pat, url):
            return url.split("?")[0]
        for short_pat in self.short_pats:
            if not re.match(short_pat, url):
                continue
            async with httpx.AsyncClient() as client:
                try:
                    self.logger.debug(f"Fetching download url for {url}")
                    resp = await client.get(url, follow_redirects=True, timeout=4)
                    self.logger.debug(f"Status code {resp.status_code}")
                    if resp.status_code != 200:
                        return None
                    real_url = str(resp.url).split("?")[0]
                    self.logger.debug(f"Returning {real_url=}")
                    return real_url
                except httpx.ConnectTimeout as e:
                    self.logger.error(f"Failed to fetch post. {url}. {e}", exc_info=e)
                    return None
                except Exception as e:
                    self.logger.error(f"Failed to fetch post. {url}. {e}", exc_info=e)
                    return None


class TwitterFetcher(Fetcher):
    TCO_REGEX = r"(https://t.co/\S+)"

    def __init__(
        self,
        key,
        secret,
        token,
        token_secret,
        web_client: ClientSession,
        twitter_client: TwitterClient,
        *args,
        **kwargs,
    ):
        self.client = PeonyClient(
            consumer_key=key,
            consumer_secret=secret,
            access_token=token,
            access_token_secret=token_secret,
        )
        self.twitter_client = twitter_client
        self.web_client = web_client
        url_pat = re.compile(
            r"(https?://)?(mobile\.|www\.)?twitter\.com/(\S+)/status/(\d+)(\?s=\d+)?(\S+)?"
        )
        super().__init__(url_pat=url_pat, short_pats=list(), *args, **kwargs)

    # Deprecated use of twitter api endpoints
    async def _fetch(self, source_url: str) -> FetchResult:
        tweet_id = self.get_tweet_id(source_url)
        try:
            tweet = await self.client.api.statuses.show.get(
                id=tweet_id, include_entities=True, tweet_mode="extended"
            )
        except exceptions.StatusNotFound:
            self.logger.info(f"Tweet {source_url} not found")
            return FetchResult(
                error_message="Tweet not found. It may have been deleted or age restricted"
            )
        except ProtectedTweet:
            self.logger.info(f"Tweet {source_url} is protected")
            return FetchResult(error_message="Tweet is protected")
        except DoesNotExist:
            self.logger.info(f"Tweet {source_url} does not exist")
            return FetchResult(
                error_message="Tweet not found. It may have been deleted or age restricted"
            )
        except HTTPNotFound:
            self.logger.info(f"Tweet {source_url} not found")
            return FetchResult(error_message="Tweet not found. Is the URL correct?")

        tweet: PeonyResponse
        tweet.user: JSONData

        poster = tweet.user["screen_name"]
        created_at = datetime.strptime(
            tweet.created_at, "%a %b %d %H:%M:%S %z %Y"
        ).replace(tzinfo=None)

        urls = self.urls_in(tweet)

        text = await self.process_urls(tweet.full_text, tweet_id)

        return FetchResult(
            post_data=PostData(source_url, poster, created_at, text, urls)
        )

    async def fetch(self, source_url: str) -> FetchResult:
        tweet_id = self.get_tweet_id(source_url)
        try:
            tweet = await self.twitter_client.get_tweet(source_url)
        except Exception as e:
            self.logger.error(f"Error fetching tweet {source_url}: {e}")
            return FetchResult(error_message="Error fetching tweet")
        if not tweet:
            return FetchResult(error_message="Tweet not found")
        tweet: Tweet
        poster = tweet.screen_name
        created_at = tweet.created_at
        urls = tweet.urls
        text = await self.process_urls(tweet.full_text, tweet_id)
        return FetchResult(
            post_data=PostData(source_url, poster, created_at, text, urls)
        )

    async def process_urls(self, text: str, source_id: int) -> str:
        """
        Get redirected urls from the tweet and exclude tweet url
        """
        urls = re.findall(self.TCO_REGEX, text)
        if not urls:
            return text

        redirected_urls = list()
        for url in urls:
            try:
                redirected_url = await asyncio.wait_for(
                    self.get_redirect(url), timeout=5
                )
                redirected_urls.append(redirected_url)
            except asyncio.TimeoutError:
                self.logger.info(f"Timeout getting redirect for {url}")
                redirected_urls.append(url)

        for url, redirected_url in zip(urls, redirected_urls):
            text = text.replace(url, redirected_url)

        tweet_matches = re.finditer(self.url_pat, text)
        for match in tweet_matches:
            if int(match.group(4)) == source_id:
                text = text.replace(match.group(0), "")

        return text

    async def get_redirect(self, url: str) -> str:
        """
        Get the real url str from a t.co url. If this fails an empty string is
        returned for the url to be replaced with
        """
        try:
            async with self.web_client.get(url) as resp:
                return str(resp.real_url)
        except ClientConnectorError:
            return ""
        except TooManyRedirects:
            return url

    def urls_in(self, tweet: PeonyResponse) -> list[str]:
        urls = list()
        if not hasattr(tweet, "extended_entities") or not hasattr(
            tweet.extended_entities, "media"
        ):
            return urls
        for media in tweet.extended_entities.media:
            if "video_info" in media:
                variants = media["video_info"]["variants"]
                bitrate_and_urls = [
                    (variant["bitrate"], variant["url"])
                    for variant in variants
                    if "bitrate" in variant
                ]
                video_url = max(bitrate_and_urls, key=lambda x: x[0])[1]
                urls.append(video_url)
            else:
                url = f"{media['media_url_https']}:orig"
                urls.append(url)
        return urls

    def get_tweet_id(self, source_url: str) -> int:
        """
        Get the tweet id from a twitter url.
        The url should be validated before calling this method.
        """
        match = re.search(self.url_pat, source_url)
        if not match:
            raise ValueError("Invalid twitter url")
        return int(match.group(4))

    def url_to_filename(self, url: str) -> str:
        """
        Create a filename for the file at the url
        """
        filename = super().url_to_filename(url)
        return filename.replace(":orig", "")


class OneTimeCookieJar(aiohttp.CookieJar):
    def __init__(self, *, unsafe: bool = False, loop: AbstractEventLoop = None) -> None:
        super().__init__(unsafe=unsafe, loop=loop)
        self._initial_cookies_loaded = False

    def update_cookies(self, cookies: LooseCookies, response_url: URL = URL()) -> None:  # type: ignore
        if not self._initial_cookies_loaded:
            super().update_cookies(cookies, response_url)

        self._initial_cookies_loaded = True

    def force_update_cookies(
        self,
        cookies: LooseCookies,
        response_url: URL = URL(),  # type: ignore
    ) -> None:
        super().update_cookies(cookies, response_url)


class InstagramFetcher(Fetcher):
    INSTAGRAM_API_URL = "https://i.instagram.com/api/v1/media/{media_id}/info/"

    def __init__(
        self,
        ig_headers: dict[str, str],
        cookies: dict[str, str],
        *args,
        **kwargs,
    ):
        self.web_client = aiohttp.ClientSession(cookie_jar=OneTimeCookieJar())
        self.web_client.cookie_jar.force_update_cookies(cookies)
        self.headers = ig_headers
        self.disabled_msg = (
            "Instagram currently not working. Bot owner has been notified"
        )
        self.disabled = False
        url_pat = re.compile(r"https?://(www.)?instagram.com/(p|tv|reel)/((\w|-)+)/?")
        super().__init__(url_pat=url_pat, short_pats=list(), *args, **kwargs)

    def shortcode_to_media_id(
        self,
        shortcode,
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_",
    ):
        base = len(alphabet)

        result = 0

        for index, char in enumerate(shortcode):
            power = len(shortcode) - (index + 1)
            result += alphabet.index(char) * (base**power)

        return result

    async def fetch(self, source_url: str) -> FetchResult:
        if self.disabled:
            return FetchResult(error_message=self.disabled_msg)
        shortcode = source_url.strip("/").split("/")[-1]
        url = self.INSTAGRAM_API_URL.format(
            media_id=self.shortcode_to_media_id(shortcode)
        )

        try:
            async with self.web_client.get(url, headers=self.headers) as response:
                try:
                    data = await response.json()
                    self.logger.debug(f"Data received: {data}")
                    for k, v in data.items():
                        self.logger.debug(f"{k}: {v}")
                except aiohttp.ContentTypeError as e:
                    self.logger.error(
                        f"Failed to fetch instagram post. {e}", exc_info=e
                    )
                    return FetchResult(error_message="Failed to fetch instagram post.")

                if data.get("message", None) == "checkpoint_required":
                    self.disabled = True
                    self.logger.error(
                        f"Instagram checkpoint required. {source_url}\n{data}"
                    )
                    return FetchResult(error_message=self.disabled_msg)
                if "spam" in data:
                    self.logger.info(f"Instagram post is spam. {source_url}\n{data}")
                    return FetchResult(error_message="Instagram post not found")
                elif "items" not in data:
                    self.logger.info(f"Instagram post not found. {source_url}\n{data}")
                    return FetchResult(error_message="Instagram post not found")

                data = data["items"][0]
                post_data = PostData(source_url)

                try:
                    post_data.text = data["caption"]["text"]
                except (KeyError, TypeError):
                    pass
                try:
                    post_data.poster = data["user"]["username"]
                except KeyError:
                    pass
                try:
                    post_data.created_at = datetime.fromtimestamp(data["taken_at"])
                except KeyError:
                    pass
        except aiohttp.TooManyRedirects as e:
            self.disabled = True
            self.logger.error(f"Failed to fetch instagram post. {e}", exc_info=e)
            return FetchResult(error_message=self.disabled_msg)

        media_entries = (
            [data] if "carousel_media" not in data else data["carousel_media"]
        )
        for media_entry in media_entries:
            media = dict()
            if media_entry["media_type"] == 1:
                media["url"] = media_entry["image_versions2"]["candidates"][0]["url"]
                post_data.urls.append(media["url"])
            elif media_entry["media_type"] == 2 and "video_versions" in media_entry:
                media["url"] = media_entry["video_versions"][0]["url"]
                post_data.urls.append(media["url"])
        return FetchResult(post_data=post_data)


class TikTokFetcher(Fetcher):
    def __init__(
        self,
        web_client: ClientSession,
        download_location: Path,
        *args,
        **kwargs,
    ):
        self.web_client = web_client
        self.download_location = download_location
        self.headers = get_config().headers
        url_pat = re.compile(r"https?://(?:www\.)?tiktok\.com/([^/]+)/video/(\d+)")
        short_pats = [
            re.compile(r"https?://vm\.tiktok\.com/([^/]+)"),
            re.compile(r"https?://(?:www\.)tiktok.com/t/([^/]+)"),
        ]
        super().__init__(url_pat, short_pats, *args, **kwargs)

    async def fetch(self, source_url: str) -> FetchResult:
        # TODO:
        # Refactor
        url = None
        if re.match(self.url_pat, source_url):
            url = source_url.split("?")[0]
        else:
            for short_pat in self.short_pats:
                if re.match(short_pat, source_url):
                    url = await self.get_download_url(source_url)
                    if not url:
                        return FetchResult(
                            error_message=(
                                "Failed to get redirect url. "
                                "Try using the full video url instead"
                            )
                        )
                    break
        if not url:
            self.logger.info(f"Invalid TikTok URL: {source_url}")
            return FetchResult(error_message="Invalid TikTok URL")

        video_id = self.url_to_id(url)
        filename = str(self.download_location / f"{video_id}.mp4")

        # Switching to TikTokApi for now
        async def yt_dlp(
            video_id: str = video_id, filename: str = filename
        ) -> tuple[str, str] | FetchResult:
            """
            Download the video using yt-dlp

            Parameters
            ----------
            video_id : str
                The video ID
            Returns
            -------
            tuple[str,str]
                Video text and filename

            """
            text_task = subprocess_run(["yt-dlp", url, "-O", "%(title)s"])
            download_task = subprocess_run(
                ["yt-dlp", "-S", "vcodec:h264", url, "-o", filename]
            )
            try:
                self.logger.debug("Downloading tiktok video")
                gathered_tasks = asyncio.gather(text_task, download_task)
                results = await asyncio.wait_for(gathered_tasks, timeout=20)
                for result in results:
                    returncode, stdout, stderr = result
                    if returncode != 0:
                        self.logger.error(f"Download failed\n{stdout}\n{stderr}")
                        return FetchResult(error_message="Download failed")

            except TimeoutError:
                self.logger.error(f"Failed to download {url}")
                return FetchResult(error_message="Download timed out")
            return results[0][1], filename

        async def tiktok_api_download(
            video_id: str = video_id, filename: str = filename, url: str = url
        ) -> tuple[str, str] | FetchResult:
            """
            Download the video using TikTokApi

            Parameters
            ----------
            video_id : str
                The video ID
            filename : str
                The filename to save the video to
            url : str
                The video URL
            Returns
            -------
            tuple[str,str]
                Video text and filename

            """
            py = "py" if sys.platform == "win32" else "python"
            cmd = [
                py,
                "rbb_bot/utils/tiktok_download.py",
                video_id,
                "-o",
                filename,
            ]
            returncode, _, stderr = await subprocess_run(cmd, timeout=20)
            if returncode != 0:
                self.logger.error(f"Failed to download TikTok video.\n{url}\n{stderr}")
                return FetchResult(error_message="Could not fetch video")
            return "", filename

        try:
            result = await yt_dlp(video_id, filename)
            if isinstance(result, FetchResult):
                # TODO: Remove dependancy on this package
                # result = await tiktok_api_download(video_id, filename, url=url)
                # if isinstance(result, FetchResult):
                # return result
                return result
            text, filename = result
        except TimeoutError:
            self.logger.error(f"Failed to download {url}. Timed out")
            return FetchResult(error_message="Download timed out")

        file_path = Path(filename)

        if not file_path.exists():
            self.logger.error(f"Failed to download {url}")
            return FetchResult(
                exception=DownloadedVideoNotFound(f"Video not found at {file_path}"),
                error_message="Download failed",
            )

        if file_path.stat().st_size > DISCORD_MAX_FILE_SIZE:
            if self.user_send:
                await self.user_send(
                    "Video size too big for discord. Compressing video"
                )
            compressed_file_path = str(
                self.download_location / f"{video_id}_compressed.mp4"
            )
            try:
                ffmpeg = FFmpeg(self.logger)
                compressed_file_path = await ffmpeg.compress(
                    file_path, compressed_file_path, DISCORD_MAX_FILE_SIZE, 120
                )
                file_path.unlink()
                file_path = compressed_file_path
            except (FFmpegError, TimeoutError) as e:
                self.logger.error(f"Failed to compress {file_path}", exc_info=e)
                file_path.unlink()
                return FetchResult(
                    exception=FFmpegError,
                    error_message="Failed to compress video",
                )

        post_data = PostData(
            url,
            text=text,
            poster=self.url_to_username(url),
            chunked_file_paths=[[str(file_path)]],
        )
        return FetchResult(post_data=post_data)

    def url_to_id(self, url: str) -> str:
        match = re.search(self.url_pat, url)
        if not match:
            self.logger.error(f"Error getting id. {url=} {match=}")
            raise ValueError("Error getting id")
        return match.group(2)

    def url_to_username(self, url: str) -> str:
        match = re.search(self.url_pat, url)
        if not match:
            self.logger.error(f"Error getting username. {url=} {match=}")
            raise ValueError("Error getting username")
        return match.group(1)


class RedditFetcher(Fetcher):
    REDDIT_VIDEO = re.compile(r"https?://v\.redd\.it/[^|/^\s]+")

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        web_client: ClientSession,
        mgck_key: str,
        *args,
        **kwargs,
    ):
        self.web_client = web_client
        self.reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        self.mgck_key = mgck_key
        url_pat = re.compile(
            r"https?://(?:www\.|old\.?)?reddit.com/r/(?:[^/]+)/comments/([^/]+)/?\S*"
        )
        short_pats = [
            re.compile(
                r"https?://(?:www\.|old\.?)?reddit.com/r/(?:[^/]+)/s/([^/]+)/?\S*"
            )
        ]
        super().__init__(url_pat=url_pat, short_pats=short_pats, *args, **kwargs)

    async def get_video_url(self, post: reddit.Submission) -> str:
        try:
            url = post.media["reddit_video"]["fallback_url"]
            url = url.split("?")[0]
            self.logger.debug(f"Got url {url}")
            return url
        except Exception as e:
            self.logger.error(
                f"Failed to get reddit video url. {post.url}. {e}", exc_info=e
            )
            return post.url

    async def get_reddit_post_urls(self, post: reddit.Submission) -> list[str]:
        urls = list()
        if "v.redd.it" in post.url:
            video_url = await self.get_video_url(post)
            urls.append(video_url)
        elif "reddit.com/gallery" in post.url:
            urls.extend(self.process_gallery(post))
        else:
            urls.append(post.url)
        self.logger.debug(f"Return urls {urls}")
        return urls

    def process_gallery(self, submission, header=""):
        links = []
        if not hasattr(submission, "media_metadata"):
            return links
        for index, i in enumerate(submission.media_metadata.items()):
            try:
                url = i[1]["p"][0]["u"]
                url = url.split("?")[0].replace("preview", "i")
                if index == 0 and header != "":
                    links.append(f"{header}\n{url}")
                else:
                    links.append(url)
            except Exception as e:
                self.logger.error(
                    f"Failed to get reddit gallery url. {submission.url}. {e}",
                    exc_info=e,
                )
        return links

    async def fetch(self, source_url: str) -> FetchResult:
        self.logger.debug(f"{source_url=}")
        url = None
        if re.match(self.url_pat, source_url):
            url = source_url.split("?")[0]
        for short_pat in self.short_pats:
            if re.match(short_pat, source_url):
                url = await self.get_download_url(source_url)
                if not url:
                    return FetchResult(error_message="Couldn't fetch the redirect url")
                break
        if url is None:
            return FetchResult(error_message="Couldn't find post id 😕")
        match = self.url_pat.search(url)
        if match is None:
            return FetchResult(error_message="Couldn't find post id 😕")
        post_id = match.group(1)
        self.logger.debug("Got post id", post_id)
        post = await self.reddit.submission(post_id)
        poster = post.author.name if post.author else "[deleted]"
        created_at = datetime.fromtimestamp(post.created_utc)
        text = f"{post.title}\n{post.selftext}"
        self.logger.debug(f"Got post {post.url} with text {text}")
        urls = list()
        if not post.is_self:
            self.logger.debug("Getting post urls")
            urls = await self.get_reddit_post_urls(post)
        if urls:
            text += "\n```" + "\n".join(urls) + "\n```"
        post_data = PostData(url, poster, created_at, text, urls)
        print(f"Created post_data\n{post_data}")
        return FetchResult(post_data=post_data)


class Sns:
    def __init__(
        self,
        fetcher: Fetcher,
        web_client: ClientSession = None,
        cache_files=True,
        timestamped_urls=False,
    ):
        self.fetcher = fetcher
        self.logger = self.fetcher.logger
        self.cache_files = cache_files
        self.timestamped_urls = timestamped_urls
        if hasattr(self.fetcher, "web_client"):
            self.web_client = self.fetcher.web_client
        else:
            self.web_client = web_client
        assert self.web_client, "No web client provided"

    def find_urls(self, text: str) -> list[str]:
        found_urls = self.fetcher.find_urls(text)
        for url in found_urls:
            self.logger.debug(f"[SNS] Found url {url}")
        # return self.fetcher.find_urls(text)
        return found_urls

    async def download_files(
        self, post_data: PostData, timestamped_urls: bool = False
    ) -> PostData:
        """
        Download and save files in post_data urls and return a new PostData
        with the file paths. Files that are over the discord size limit are
        not saved and their urls are kept in the new PostData.

        Parameters
        ----------
        post_data : PostData
            The post data
        timestamped_urls : bool
            Whether the urls are timestamped. If true and any of the media is over
            the discord size limit, none of the files will be downloaded.
        """
        undownloadable_urls = list()
        bytes_and_paths = list()

        chunked_media = list()
        media_chunk = list()
        chunked_file_paths = list()
        file_chunk = list()
        chunk_size = 0
        att_num = 0

        for url in post_data.urls:
            if not self.is_downloadable(url):
                undownloadable_urls.append(url)
                continue
            try:
                filename = self.fetcher.url_to_filename(url)
            except Exception as e:
                self.logger.error(
                    f"Failed to get filename from url. {url}. {e}", exc_info=e
                )
                continue

            file_bytes = BytesIO(
                await http_get(self.web_client, URL(url, encoded=True))
            )
            fsize = file_bytes.getbuffer().nbytes
            if fsize > DISCORD_MAX_FILE_SIZE:
                undownloadable_urls.append(url)
                continue
            file_path = Path(FilePaths.CACHE_DIR, filename)
            bytes_and_paths.append((file_bytes, file_path))
            att_num += 1

            if (
                fsize + chunk_size
            ) > DISCORD_MAX_FILE_SIZE or att_num >= MAX_ATTACHMENTS:
                chunked_file_paths.append(file_chunk)
                chunked_media.append(media_chunk)
                file_chunk = [str(file_path)]
                media_chunk = [PostMedia(filename=filename, bytes_io=file_bytes)]
                chunk_size = fsize
                att_num = 0
            else:
                chunk_size += fsize
                file_chunk.append(str(file_path))
                media_chunk.append(PostMedia(filename=filename, bytes_io=file_bytes))

        if file_chunk or media_chunk:
            chunked_file_paths.append(file_chunk)
            chunked_media.append(media_chunk)

        new_data = PostData(
            post_data.source_url,
            post_data.poster,
            post_data.created_at,
            post_data.text,
            undownloadable_urls,
        )

        if timestamped_urls and undownloadable_urls:
            new_data.chunked_media = chunked_media
            return new_data
        else:
            for x in bytes_and_paths:
                data, file_path = x
                with open(file_path, "wb") as f:
                    f.write(data.read())

            new_data.chunked_file_paths = chunked_file_paths
            if post_data.chunked_file_paths:
                new_data.chunked_file_paths.extend(post_data.chunked_file_paths)
            return new_data

    def is_downloadable(self, url: str) -> bool:
        skip_urls = ["https://i.imgur", "https://imgur"]
        for skip_url in skip_urls:
            if url.startswith(skip_url):
                return False
        return True

    async def fetch(self, source_url: str) -> FetchResult:
        """
        Fetch the post data from the source url

        Parameters
        ----------

        source_url: str
            The url to fetch the post data from
        """
        self.logger.debug(f"fetch recieved {source_url}")
        if not self.cache_files:
            return await self.fetcher.fetch(source_url)

        # Get cached data
        saved_data = await DiskCache.get_or_none(key=source_url)
        if saved_data:
            self.logger.debug(f"Found cached data for {source_url}")
            saved_data.accessed_at = datetime.utcnow()
            await saved_data.save()
            return FetchResult(
                post_data=PostData.from_dict(saved_data.value),
            )

        # Not cached. Fetch data
        self.logger.debug(f"Not cached. Fetching data for {source_url}")
        fetch_result = await self.fetcher.fetch(source_url)
        post_data = fetch_result.post_data

        if not post_data:
            self.logger.debug(f"No data found. Skipping caching for {source_url}")
            return fetch_result
        self.logger.debug(f"Got data: {post_data}")

        # Download files and get modified post_data
        post_data = await self.download_files(post_data, self.timestamped_urls)

        skip_cache = self.timestamped_urls and (
            post_data.chunked_media or post_data.urls
        )
        if not skip_cache:
            # Create cache
            self.logger.debug(f"Caching data for {source_url}")
            entry = await DiskCache.create(key=source_url, value=post_data.as_dict())
            self.logger.debug(f"Created entry for {source_url}. {entry=}")
            if (await DiskCache.all().count()) > DiskCache.MAX_SIZE:
                self.logger.debug("DiskCache is full. Deleting oldest entry.")
                oldest = await DiskCache.all().order_by("accessed_at").first()
                self.logger.debug(f"Deleting {oldest}")
                for chunk in oldest.value["chunked_file_paths"]:
                    for file_path in chunk:
                        Path(file_path).unlink(missing_ok=True)
                await oldest.delete()
        else:
            self.logger.debug(f"Skipping caching for {source_url}")

        fetch_result.post_data = post_data
        return fetch_result

    def format_post(
        self, post_data: PostData, with_text: bool = False
    ) -> list[SnsMessage]:
        text = ""

        if with_text:
            if post_data.poster:
                text = f"`{post_data.poster}` posted "
            if post_data.created_at:
                text = f"{text}at {format_dt(post_data.created_at, style='f')}"
            if post_data.text:
                text = f"{text}\n{post_data.text}"
            text = f"{text}\n"

            text = re.sub(r"\n{2,}", "\n", text)
            text = re.sub(r"\s{2,}", " ", text)

        # First message with text (if any) and urls (if any)
        # If no urls are present but chunked_file_paths or chunked_media are
        # then the first chunk is attached
        chunked_urls = list(chunker(post_data.urls, 5, DISCORD_MAX_MESSAGE))
        url_str = ""
        if chunked_urls:
            url_str = "\n".join(chunked_urls.pop(0))
        if len(text) + len(url_str) > DISCORD_MAX_MESSAGE:
            text = truncate(text, DISCORD_MAX_MESSAGE - len(url_str) - 5)
        first_message = SnsMessage(text, url_str)

        if not url_str:
            if post_data.chunked_file_paths:
                first_message.file_paths = post_data.chunked_file_paths.pop(0)
            if post_data.chunked_media:
                first_message.media = post_data.chunked_media.pop(0)
        messages = [first_message]

        # Subsequent messages with either urls or file_paths
        for chunk in chunked_urls:
            url_str = "\n".join(chunk)
            messages.append(SnsMessage(url_str))
        for chunk in post_data.chunked_file_paths:
            messages.append(SnsMessage(content="", file_paths=chunk))
        for chunk in post_data.chunked_media:
            messages.append(SnsMessage(content="", media=chunk))

        messages = [
            x for x in messages if x.content or x.file_paths or x.media or x.url_str
        ]
        return messages
