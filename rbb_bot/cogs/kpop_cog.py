import asyncio
import re
import urllib.parse
from typing import List, Optional
import dateparser

import pendulum
from bs4 import BeautifulSoup
from discord import Embed
from discord.ext import commands
from discord.ext import tasks
from discord.ext.commands import Context, Cog
from discord.utils import format_dt
from models import Release
from tortoise.expressions import Q
from utils.helpers import http_get
from utils.helpers import truncate
from utils.scraper import Scraper
from utils.views import ListView, SearchResultsView, SearchResult


class VideoList(ListView):
    def create_message(self, results: tuple[str, Release]) -> str:
        header = f"Page {self.current_page + 1} of {len(self.view_chunks)}\n"
        body = list()
        for result in results:
            video, release = result
            artist_name = truncate(release.artist.name, 30)
            title = truncate(release.title, 30)
            if release.release_time:
                date_or_time = format_dt(release.release_time, style="f")
            else:
                date_or_time = f"**{release.release_date}**"
            body.append(f"{date_or_time}\n{artist_name} - {title}\n{video}")
        return header + "\n".join(body)


class YoutubeList(ListView):
    def create_message(self, results: list[str]) -> str:
        header = f"Page {self.current_page + 1} of {len(self.view_chunks)}\n"
        body = list()
        for result in results:
            body.append(result)
        return header + "\n".join(body)


class ReleasesView(ListView):
    YT_URL = re.compile(
        r"(?:https?://)?(?:www\.)?youtu(?:be\.com/watch\?v=|\.be/)([\w-]{11})"
    )

    def create_embed(self, releases: List[Release]) -> Embed:
        def format_release_field(r: Release) -> tuple[str, str]:
            release_time = (
                format_dt(r.release_time, "f") if r.release_time else r.date_string
            )

            artist_name = truncate(r.artist.name, 80)

            title_and_album = ""
            if r.title == r.album_title:
                title_and_album = r.title
            else:
                if r.title:
                    title_and_album += r.title
                if r.album_title:
                    title_and_album += (
                        f" ({r.album_title})" if title_and_album else r.album_title
                    )

            title_and_album = truncate(title_and_album, 80)
            release_type = f"*[{r.release_type.name}]*" if r.release_type.name else ""
            value_ = f"`{artist_name}`\n{title_and_album}"
            if release_type:
                value_ += f"\n{release_type}"
            if r.urls:
                for url in r.urls[:4]:
                    if match := self.YT_URL.search(url):
                        value_ += f"\nhttps://youtu.be/{match.group(1)}"
                    else:
                        value_ += f"\n{url}"
            return release_time, value_

        embed = Embed(title=f"Page {self.current_page + 1} of {len(self.view_chunks)}")
        header_name = f"{len(self.list_items)} {'releases' if len(self.list_items) > 1 else 'release'}"
        header_value = "Times displayed in your local timezone"
        embed.add_field(name=header_name, value=header_value, inline=False)
        for release in releases:
            name, value = format_release_field(release)
            value = f"{value}\n{'-' * 50}"
            embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text=f"Source: https://www.reddit.com/r/kpop")
        return embed


class KpopCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.YT_ID = re.compile(r"v=([a-zA-Z0-9_-]{11})")
        self.kprofiles_url = self.bot.config.kprofiles_url
        self.search_key = self.bot.creds.search_key
        self.scraper = Scraper(
            web_client=self.bot.web_client,
            headers=self.bot.config.headers,
            logger=self.bot.logger,
            creds=self.bot.creds,
        )
        self.update_comebacks_task.start()

    @tasks.loop(hours=6)
    async def update_comebacks_task(self) -> None:
        await self.scraper.scrape()

    @update_comebacks_task.before_loop
    async def before_update_comebacks_task(self) -> None:
        await self.bot.wait_until_ready()

    async def cog_load(self) -> None:
        self.bot.logger.debug("kpop Cog loaded!")

    async def cog_unload(self) -> None:
        await self.scraper.reddit.close()
        self.update_comebacks_task.cancel()
        self.bot.logger.debug("kpop Cog unloaded!")

    @commands.hybrid_command(brief="Update the comebacks database")
    @commands.is_owner()
    async def update_comebacks(self, ctx: Context) -> None:
        await ctx.send("Starting update...")
        await self.scraper.scrape()
        await ctx.send("Done!")

    @commands.hybrid_command(
        brief="Search through MV links stored in the database. "
        "Either artist or release name is required"
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def videos(
        self, ctx: Context, artist: Optional[str], release_name: Optional[str]
    ):
        """
        Search through MV links stored in the database. Either artist or release name is required

        Parameters
        ----------

        artist: Optional[str]
            Artist to search for (Optional)
        release_name: Optional[str]
            Title to search for (Optional)
        """
        waited = 0
        async with ctx.typing():
            while self.scraper.updating:
                await asyncio.sleep(1)
                waited += 1
                if waited > 3:
                    self.bot.logger.error(
                        comment="Scraper is taking too long to update"
                    )
                    break
        if artist is None and release_name is None:
            return await ctx.send(
                "Please provide an artist or a release name to search for."
            )
        filters = list()
        if artist:
            filters.append(Q(artist__name__icontains=artist))
        if release_name:
            filters.append(Q(title__icontains=release_name))

        releases = (
            await Release.filter(*filters)
            .order_by("-release_date")
            .prefetch_related("artist", "release_type")
        )
        releases = [r for r in releases if r.urls]
        if not releases:
            return await ctx.send("No releases found.")

        formatted_results = list()
        for release in releases:
            for url in release.urls:
                formatted_results.append((url, release))

        view = VideoList(ctx, formatted_results, chunk_size=2)
        init_message = view.create_message(view.current_chunk)
        view.message = await ctx.send(init_message, view=view)

    @commands.hybrid_command(brief="Search youtube and return the top results.")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def youtube(self, ctx: Context, *, query: str):
        """
        Search youtube and return the top results.

        Parameters
        ----------

        query: str
            Query to search for (Required)
        """
        query = urllib.parse.quote(query)
        html = await http_get(
            self.bot.web_client,
            f"https://www.youtube.com/results?search_query={query}",
            as_text=True,
        )
        results = self.YT_ID.findall(html)
        video_urls = list()
        for r in results:
            url = f"https://www.youtube.com/watch?v={r}"
            if url not in video_urls:
                video_urls.append(url)
        if not video_urls:
            return await ctx.send("No results found.")

        view = YoutubeList(ctx, video_urls[:20], chunk_size=2)
        content = view.create_message(view.current_chunk)
        view.message = await ctx.send(content, view=view)

    @commands.hybrid_command(brief="Search kprofiles")
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def kprofiles(self, ctx: Context, *, query: str):
        """
        Search kprofiles

        Parameters
        ----------

        query: str
            Query to search for (Required)
        """
        query = urllib.parse.quote(query)
        url = self.kprofiles_url.format(apikey=self.search_key, query=query)
        response = await http_get(self.bot.web_client, url, as_json=True)
        search_results = [SearchResult(item) for item in response["items"][:5]]
        view = SearchResultsView(ctx, search_results, 1)
        view.embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=view.embed, view=view)

    @commands.hybrid_command(
        brief="Show recent and upcoming releases", alias=["cbs", "cb", "comeback"]
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def comebacks(
        self,
        ctx: Context,
        artist: Optional[str] = None,
        release_name: Optional[str] = None,
        release_type: Optional[str] = None,
        start_date: Optional[str] = None,
    ):
        """
        Shows upcoming releases

        Parameters
        ----------
        artist: str
            Filter by this artist (Optional) - Partial match
        release_name: str
            Filter by releases or albums containing this name (Optional) - Partial match
        release_type: str
            Filter by this release type (Optional) - Partial match
        start_date: str
             Show comebacks from this date onwards. Earliest=2018-01-01 (Optional)
        """
        waited = 0
        async with ctx.typing():
            while self.scraper.updating:
                await asyncio.sleep(1)
                waited += 1
                if waited > 4:
                    self.bot.logger.error(
                        comment="Scraper is taking too long to update"
                    )
                break

        self.bot.logger.debug("Adding filters")
        filters = list()
        if artist:
            self.bot.logger.debug(f"Artist filter {artist}")
            filters.append(Q(artist__name__icontains=artist))
        if release_name:
            self.bot.logger.debug(f"Release filter {release_name}")
            filters.append(
                Q(title__icontains=release_name)
                | Q(album_title__icontains=release_name)
            )
        if release_type:
            self.bot.logger.debug(f"Release type filter {release_type}")
            filters.append(Q(release_type__name__icontains=release_type))

        parsed_date = None
        if start_date:
            self.bot.logger.debug(f"Start date filter {start_date}")
            parsed_date = dateparser.parse(start_date)
            self.bot.logger.debug(f"Parsed date: {parsed_date}")
            if not parsed_date:
                await ctx.send(
                    f"Sorry I could not understand start date: {start_date}. "
                    "Looking for releases from 2 days ago"
                )

        if parsed_date:
            filters.append(Q(release_date__gte=parsed_date))
        else:
            filters.append(Q(release_date__gte=pendulum.today().add(days=-2)))

        releases = (
            await Release.filter(*filters, join_type="AND")
            .order_by("release_date")
            .prefetch_related("artist", "release_type")
        )

        async def send_releases(ctx, releases):
            view = ReleasesView(ctx, releases)
            embed = view.create_embed(view.current_chunk)
            view.message = await ctx.send(embed=embed, view=view)
            return view.message

        if start_date:
            if releases:
                return await send_releases(ctx, releases)
            else:
                return await ctx.send("No releases found.")

        if releases:
            return await send_releases(ctx, releases)

        filters[-1] = Q(release_date__lt=pendulum.today())
        releases = (
            await Release.filter(*filters, join_type="AND")
            .order_by("-release_date")
            .prefetch_related("artist", "release_type")
        )
        if not releases:
            return await ctx.send("No releases found")
        else:
            await ctx.send(f"No recent releases found. Showing older releases")
            return await send_releases(ctx, releases)

    @commands.hybrid_command(
        brief="Post a random YouTube comment from a kpop music video",
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def ytc(self, ctx: Context) -> None:
        """
        Post a random YouTube comment from a kpop music video
        Source: https://dbkpop.com/random-kpop-youtube-comment-generator/
        """
        url = "https://dbkpop.com/random-kpop-youtube-comment-generator/"
        async with self.bot.web_client.get(url) as response:
            if response.status == 200:
                soup = BeautifulSoup(await response.read(), "html.parser")
                try:
                    await ctx.send(
                        soup.select(selector=".quotescollection-quote")[0].text
                    )
                except Exception as e:
                    self.bot.logger.error(
                        "Error getting random youtube comment",
                        exc_info=e,
                        stack_info=True,
                    )
            else:
                self.bot.logger.error(
                    f"Could not fetch random youtube comment. {response.status=}"
                )
                await ctx.send("Could not get a comment")


async def setup(bot):
    await bot.add_cog(KpopCog(bot))
