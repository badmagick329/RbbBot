from typing import Optional

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context
from settings.const import FilePaths, DISCORD_MAX_FILE_SIZE
from utils.sns import (
    TwitterFetcher,
    InstagramFetcher,
    TikTokFetcher,
    RedditFetcher,
    Sns,
)
from utils.views import SnsMenu
from discord.ext.menus import CannotSendMessages


class SnsCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        twitter_fetcher = TwitterFetcher(
            self.bot.creds.twitter_key,
            self.bot.creds.twitter_secret,
            self.bot.creds.twitter_token,
            self.bot.creds.twitter_token_secret,
            self.bot.web_client,
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
            FilePaths.CACHE_DIR,
            logger=self.bot.logger,
        )
        self.sns_dict = {
            "twitter": Sns(twitter_fetcher, self.bot.logger),
            "instagram": Sns(instagram_fetcher, self.bot.logger, timestamped_urls=True),
            "tiktok": Sns(tiktok_fetcher, self.bot.logger),
            "reddit": Sns(reddit_fetcher, self.bot.logger, cache_files=False),
        }

    async def cog_load(self):
        self.bot.logger.debug("SnsCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("SnsCog unloaded!")
        self.instagram_fetcher.web_client.close()

    def not_found_message(self, sns_name, url):
        if sns_name == "twitter":
            return f"Could not find tweet at {url}. If the tweet is a retweet, try the original tweet."
        if sns_name == "instagram":
            return f"Could not find media at {url}. Instagram stories are not supported"
        if sns_name == "tiktok":
            return (
                f"Could not find video at {url}. Photos and Stories are not supported. "
                f"If the video is above discord size limit ({DISCORD_MAX_FILE_SIZE/1024/1024}MB), it will not be posted"
            )
        if sns_name == "reddit":
            return f"Could not find post at {url}"

    @commands.hybrid_command(
        name="sns", brief="Get posts from twitter, ig, tiktok or reddit"
    )
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def sns_cmd(
        self, ctx: Context, with_text: Optional[bool] = False, *, urls: str
    ):
        """
        Get posts from twitter, ig, tiktok or reddit

        Not supported: ig stories, tiktok photos, reddit videos with sound

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
            for sns_name, sns in self.sns_dict.items():
                found_urls = sns.find_urls(urls)
                messages = list()
                for url in found_urls:
                    post_data = await sns.fetch(url)
                    if not post_data or post_data.is_empty:
                        error_messages.append(self.not_found_message(sns_name, url))
                        continue
                    messages.extend(sns.format_post(post_data, with_text=with_text))
                sns_messages.extend(messages)

            if not sns_messages:
                if error_messages:
                    await ctx.send("\n".join(error_messages))
                else:
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
            if not (ctx.me.guild_permissions.add_reactions):
                return
            if not (
                ctx.me.guild_permissions.embed_links
                and ctx.me.guild_permissions.send_messages
            ):
                return
            found_urls = False
            for sns_name, sns in self.sns_dict.items():
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
        except CannotSendMessages:
            pass
        except Exception as e:
            await self.bot.send_error(
                exc=e, comment=f"sns on_message\n{message.content}", stack_info=True
            )


async def setup(bot):
    await bot.add_cog(SnsCog(bot))
