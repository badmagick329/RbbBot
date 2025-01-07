from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context
from discord.ext.menus import (CannotAddReactions, CannotEmbedLinks,
                               CannotSendMessages)
from settings.const import FilePaths
from utils.sns import (InstagramFetcher, RedditFetcher, Sns, TikTokFetcher,
                       TwitterFetcher)
from utils.twitter import TwitterClient
from utils.views import SnsMenu

from rbb_bot.utils.decorators import log_command


class SnsCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        twitter_client = TwitterClient(
            web_client=self.bot.web_client,
            api_key=self.bot.creds.rapid_api_key,
            logger=self.bot.logger,
        )
        twitter_fetcher = TwitterFetcher(
            self.bot.creds.twitter_key,
            self.bot.creds.twitter_secret,
            self.bot.creds.twitter_token,
            self.bot.creds.twitter_token_secret,
            self.bot.web_client,
            twitter_client,
            logger=self.bot.logger,
        )
        instagram_fetcher = InstagramFetcher(
            self.bot.config.ig_headers,
            self.bot.creds.ig_cookies,
            logger=self.bot.logger,
        )
        tiktok_fetcher = TikTokFetcher(
            self.bot.web_client,
            FilePaths.CACHE_DIR,
            logger=self.bot.logger,
        )
        reddit_fetcher = RedditFetcher(
            self.bot.creds.reddit_id,
            self.bot.creds.reddit_secret,
            self.bot.creds.reddit_agent,
            self.bot.web_client,
            self.bot.creds.mgck_key,
            logger=self.bot.logger,
        )
        self.sns_dict = {
            # "twitter": Sns(twitter_fetcher),
            # "instagram": Sns(instagram_fetcher, timestamped_urls=True),
            "tiktok": Sns(tiktok_fetcher),
            "reddit": Sns(reddit_fetcher, cache_files=True),
        }

    async def cog_load(self):
        self.bot.logger.debug("SnsCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("SnsCog unloaded!")
        self.instagram_fetcher.web_client.close()

    @commands.hybrid_command(name="sns", brief="Get posts from tiktok or reddit")
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(2, 5, commands.BucketType.user)
    @log_command(command_name="sns")
    async def sns_cmd(
        self, ctx: Context, with_text: Optional[bool] = False, *, urls: str
    ):
        """
        Get posts from tiktok or reddit

        Not supported: tiktok photos, reddit videos with sound

        Parameters
        ----------
        urls : str
            The urls of posts (Required)
        with_text: str
            Get post text (default=False)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        async with ctx.typing():
            sns_messages = list()
            error_messages = list()
            all_found_urls = list()
            for sns_name, sns in self.sns_dict.items():
                found_urls = sns.find_urls(urls)
                if found_urls:
                    self.bot.logger.debug(f"Found {sns_name} urls: {found_urls}")
                messages = list()
                sns.fetcher.user_send = ctx.send

                for url in found_urls:
                    fetch_result = await sns.fetch(url)
                    post_data = fetch_result.post_data
                    if not post_data or post_data.is_empty:
                        error_messages.append(fetch_result.error_message)
                        continue
                    messages.extend(sns.format_post(post_data, with_text=with_text))
                sns_messages.extend(messages)
                all_found_urls.extend(found_urls)

            if not sns_messages:
                if error_messages:
                    await ctx.send("\n".join(error_messages))
                else:
                    url_str = "\n".join(all_found_urls)
                    self.bot.logger.info(f"No posts found at {url_str}")
                    return await ctx.send("No posts found")

            try:
                await ctx.message.edit(suppress=True)
            except (discord.Forbidden, discord.NotFound):
                pass

            for message in sns_messages:
                await message.send(ctx)

    @Cog.listener()
    async def on_message(self, message):
        try:
            if message.author.bot:
                return
            ctx = await self.bot.get_context(message)
            if ctx.command:
                return
            found_urls = False
            for _, sns in self.sns_dict.items():
                if sns.find_urls(message.content):
                    found_urls = True
                    break
            if not found_urls:
                return

            result = await SnsMenu(message).prompt(ctx)
            if not result:
                return
            if result == "no_text":
                await self.sns_cmd(ctx, with_text=False, urls=message.content)
            else:
                await self.sns_cmd(ctx, with_text=True, urls=message.content)
        except (CannotSendMessages, CannotAddReactions, CannotEmbedLinks):
            pass
        except Exception as e:
            await self.bot.send_error(
                exc=e, comment=f"sns on_message\n{message.content}"
            )


async def setup(bot):
    await bot.add_cog(SnsCog(bot))
