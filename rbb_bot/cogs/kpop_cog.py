import asyncio
import re
import urllib.parse
from typing import Optional

import dateparser
from bs4 import BeautifulSoup
from discord import AllowedMentions
from discord.ext import commands, tasks
from discord.ext.commands import Cog, Context

from rbb_bot.application.releases.contracts import ReleaseFilter
from rbb_bot.application.releases.lookup import (
    FindVideos,
    ListReleases,
    SearchTermMissing,
)
from rbb_bot.application.wins.latest import (
    InvalidArtist,
    WinsUnavailable,
    normalize_artist,
)
from rbb_bot.infrastructure.releases.repository import ReleaseRepository
from rbb_bot.infrastructure.releases.scraper import Scraper
from rbb_bot.utils.helpers import http_get
from rbb_bot.utils.views import ListView, SearchResult, SearchResultsView
from rbb_bot.views.releases import ReleasesView, VideoList
from rbb_bot.views.wins import wins_embed


class YoutubeList(ListView):
    def create_message(self, current_chunk: list[str]) -> str:
        header = f"Page {self.current_page + 1} of {len(self.view_chunks)}\n"
        body = list()
        for result in current_chunk:
            body.append(result)
        return header + "\n".join(body)


class KpopCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.YT_ID = re.compile(r"v=([a-zA-Z0-9_-]{11})")
        self.kprofiles_url = self.bot.config.kprofiles_url
        self.search_key = self.bot.creds.search_key
        self.repository = ReleaseRepository()
        self.scraper = Scraper(
            web_client=self.bot.web_client,
            headers=self.bot.config.headers,
            logger=self.bot.logger,
            creds=self.bot.creds,
        )

    @tasks.loop(hours=6)
    async def update_comebacks_task(self) -> None:
        try:
            await self.scraper.scrape()
        except Exception:
            # Do not let one failed run permanently stop the six-hour task.
            # logger.exception includes the traceback and is forwarded to the
            # operational Discord log channel by the normal log handler.
            self.bot.logger.exception("Scheduled release scraper failed")

    @update_comebacks_task.error
    async def update_comebacks_task_error(self, error: Exception) -> None:
        """Report a task-level failure that escaped the scheduled run."""
        self.bot.logger.error(
            "Scheduled release scraper task stopped unexpectedly",
            exc_info=(type(error), error, error.__traceback__),
        )

    @update_comebacks_task.before_loop
    async def before_update_comebacks_task(self) -> None:
        await self.bot.wait_until_ready()
        await self.bot.logging_ready.wait()

    async def cog_load(self) -> None:
        self.update_comebacks_task.start()
        self.bot.logger.debug("kpop Cog loaded!")

    async def cog_unload(self) -> None:
        task = self.update_comebacks_task.get_task()
        self.update_comebacks_task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await self.scraper.reddit.close()
        self.bot.logger.debug("kpop Cog unloaded!")

    async def update_comebacks(self, ctx: Context, urls: Optional[str] = None) -> None:
        if not urls:
            urls = None
        else:
            urls = [u.strip() for u in urls.split(" ") if u.strip()]
        await ctx.send("Starting update...")
        completed = await self.scraper.scrape(urls=urls)
        await ctx.send(
            "Done!" if completed else "Update failed; stored releases were preserved"
        )

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
                    self.bot.logger.error("Scraper is taking too long to update")
                    break
        try:
            videos = await FindVideos(self.repository).execute(artist, release_name)
        except SearchTermMissing:
            return await ctx.send(
                "Please provide an artist or a release name to search for."
            )
        if not videos:
            return await ctx.send("No releases found.")

        view = VideoList(ctx, list(videos), chunk_size=2)
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
        response = await http_get(url, as_json=True)
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
             Show releases from this date onwards. Earliest=2018-01-01 (Optional)
        """
        waited = 0
        async with ctx.typing():
            while self.scraper.updating:
                await asyncio.sleep(1)
                waited += 1
                if waited > 4:
                    self.bot.logger.error("Scraper is taking too long to update")
                break

        criteria = ReleaseFilter(
            artist=artist, title_or_album=release_name, release_type=release_type
        )
        self.bot.logger.debug(f"Release filter {criteria}")

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

        found = await ListReleases(self.repository).execute(
            criteria, start=parsed_date, start_requested=bool(start_date)
        )
        if not found.releases:
            # The two wordings differ only by the full stop; kept as the command sent them.
            return await ctx.send(
                "No releases found" if found.showing_older else "No releases found."
            )
        if found.showing_older:
            await ctx.send("No recent releases found. Showing older releases")
        view = ReleasesView(ctx, list(found.releases))
        embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=embed, view=view)
        return view.message

    @commands.hybrid_command(brief="Show the latest recorded music-show wins")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def wins(self, ctx: Context, *, artist: Optional[str] = None) -> None:
        """Show five latest recorded wins, optionally by exact artist name or alias.

        Parameters
        ----------
        artist: Optional[str]
            Exact artist name or known alias (up to 100 characters).
        """
        if ctx.interaction is not None:
            await ctx.defer()
        try:
            artist = normalize_artist(artist)
        except InvalidArtist as error:
            await ctx.send(
                f"{error}\nhttps://kpopwins.info/wins",
                allowed_mentions=AllowedMentions.none(),
            )
            return
        try:
            wins = await self.bot.latest_wins.execute(artist)
        except WinsUnavailable:
            embed = wins_embed(artist=artist, unavailable=True)
        else:
            embed = wins_embed(wins, artist=artist)
        await ctx.send(embed=embed, allowed_mentions=AllowedMentions.none())

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
