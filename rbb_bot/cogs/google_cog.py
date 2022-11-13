import urllib.parse
from dataclasses import dataclass
from typing import List, Optional

from discord import Embed
from discord.ext import commands
from discord.ext.commands import Context, Cog
from utils.helpers import http_get
from utils.views import ListView


@dataclass
class GoogleResult:
    title: str
    link: str
    description: str
    image_only: bool

    def __init__(self, item: dict, image_only: bool = False):
        self.title = item["title"]
        self.link = item["link"]
        self.description = item["snippet"]
        self.image_only = image_only


class GoogleResultsView(ListView):
    def create_embed(self, results: List[GoogleResult]) -> Embed:
        embed = Embed(
            title=f"Google Results page {self.current_page + 1} of {len(self.view_chunks)}"
        )
        for result in results:
            if result.image_only:
                embed.set_image(url=result.link)
            else:
                embed.add_field(
                    name=result.title, value=result.description, inline=False
                )
                embed.add_field(name="Link", value=result.link, inline=False)
        return embed


class GoogleCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = self.bot.creds.search_key
        self.google_url = self.bot.config.google_url

    async def cog_load(self) -> None:
        self.bot.logger.info("GoogleCog loaded")

    async def cog_unload(self) -> None:
        self.bot.logger.info("GoogleCog unloaded")

    @commands.hybrid_command(brief="Search google", aliases=["g"])
    @commands.cooldown(3, 10, commands.BucketType.user)
    @commands.has_permissions(manage_messages=True)
    async def google(
        self, ctx: Context, image_only: Optional[bool], *, query: str
    ) -> None:
        """
        Search google for a query

        Parameters
        ----------
        image_only: bool
            Return images only (Default: False)
        query: str
            The query to search for (Required)
        """
        query = urllib.parse.quote(query)
        url = self.google_url.format(apikey=self.api_key, query=query)
        if image_only:
            url += "&searchType=image"
        response = await http_get(self.bot.web_client, url, as_json=True)
        search_results = [
            GoogleResult(item, image_only) for item in response["items"][:10]
        ]
        view = GoogleResultsView(ctx, search_results, 1)
        view.embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=view.embed, view=view)


async def setup(bot):
    await bot.add_cog(GoogleCog(bot))
