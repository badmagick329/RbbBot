import asyncio
import re
from datetime import datetime
from typing import Any, Optional

import aiohttp


class Tweet:
    data: dict[str, Any]
    screen_name: str
    full_text: str
    urls: list[str]
    created_at: datetime

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.screen_name = data["core"]["user_result"]["result"]["legacy"][
            "screen_name"
        ]
        try:
            medias = data["legacy"]["extended_entities"]["media"]
        except KeyError:
            medias = list()
        self.full_text = data["legacy"]["full_text"]
        self.created_at = datetime.strptime(
            data["legacy"]["created_at"], "%a %b %d %H:%M:%S %z %Y"
        ).replace(tzinfo=None)
        self.urls = list()
        for media in medias:
            if "video_info" in media:
                variants = media["video_info"]["variants"]
                bitrate_and_urls = [
                    (variant["bitrate"], variant["url"])
                    for variant in variants
                    if "bitrate" in variant
                ]
                video_url = max(bitrate_and_urls, key=lambda x: x[0])[1]
                self.urls.append(video_url)
            else:
                url = f"{media['media_url_https']}:orig"
                self.urls.append(url)

    def __repr__(self):
        return f"Tweet(screen_name={self.screen_name}, full_text={self.full_text}, urls={self.urls}, created_at={self.created_at})"


class TwitterClient:
    RAPID_API_URL = "https://twttrapi.p.rapidapi.com"
    URL_REGEX = (
        r"(https?://)?(mobile\.|www\.)?twitter\.com/(\S+)/status/(\d+)(\?s=\d+)?(\S+)?"
    )

    def __init__(self, web_client: aiohttp.ClientSession, api_key: str, logger: Any):
        self.web_client = web_client
        self.headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "twttrapi.p.rapidapi.com",
        }
        self.last_fetch = datetime.now()
        self.logger = logger

    async def get_tweet(self, source_url: str) -> Optional[Tweet]:
        match = re.search(self.URL_REGEX, source_url)
        if not match:
            self.logger.error(f"get_tweet: Invalid URL. URL: {source_url}")
            return None
        tweet_id = int(match.group(4))
        if (datetime.now() - self.last_fetch).seconds < 1:
            await asyncio.sleep(1)
        url = f"{self.RAPID_API_URL}/get-tweet"
        params = {"tweet_id": tweet_id}
        try:
            async with self.web_client.get(
                url, headers=self.headers, params=params
            ) as response:
                json = await response.json()
                if errors := json.get("errors", None):
                    if self.logger:
                        self.logger.error(f"Errors: {errors}. Tweet: {source_url}")
                    else:
                        print(f"Errors: {errors}")
                    return None
                result = json["data"]["tweet_result"]["result"]
                self.last_fetch = datetime.now()
                tweet = Tweet(result)
                return tweet
        except Exception as e:
            if self.logger:
                self.logger.error(f"Exception: {e}. Tweet: {source_url}")
            else:
                print(e)
            return None
