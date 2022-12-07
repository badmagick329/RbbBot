import random
import urllib
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

import discord
from discord import User
from discord.ext import commands
from discord.ext.commands import Cog, Context
from discord.utils import format_dt
from utils.helpers import (channel_regex, emoji_regex, emoji_url, http_get,
                           role_regex, truncate, user_regex)
from utils.views import SearchResult, SearchResultsView


class MiscCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.wiki_url = self.bot.config.wiki_url
        self.search_key = self.bot.creds.search_key

    async def cog_load(self):
        self.bot.logger.debug("MiscCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("MiscCog unloaded!")

    @commands.hybrid_command(
        brief="Show create date for discord snowflakes", aliases=["sf"]
    )
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def snowflake(self, ctx, snowflakes: str):
        """
        Get create date for discord snowflakes separated by spaces.
        These can also be emojis, user mentions, channel mentions, or role mentions.

        Parameters
        ----------
        snowflakes: str
            Discord snowflakes to get create date for. These can also be emojis (Required)
        """
        results = list()
        for arg in snowflakes.split(" "):
            if len(results) >= 10:
                break
            obj = get_snowflake_data(arg.strip(), self.bot)
            if obj is None or obj in results:
                continue
            results.append(obj)

        if not results:
            return await ctx.send("No valid snowflakes found.")

        msg = list()
        if len(results) == 10:
            msg.append("Displaying the first 10 results")
        for result in results:
            type_ = f'{result["type"]} ' if result["type"] else ""
            string = f'{result["str"]} ' if result["str"] else ""
            created_at = f'created at {format_dt(result["created"])}'
            msg.append(f"{type_}{string}{created_at}")

        await ctx.send("\n".join(msg))

    @commands.hybrid_command(brief="Mockify text")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def mock(self, ctx: Context, *, text: str):
        """
        Mockify text

        Parameters
        ----------
        text: str
            Text to mockify (Required)
        """
        mocked = "".join(
            [c.upper() if random.randint(0, 1) else c for c in text.lower()]
        )
        await ctx.send(truncate(mocked))

    @commands.hybrid_command(brief="Choose between multiple options separated by ,")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def choose(self, ctx: Context, *, options: str):
        """
        Choose between multiple options separated by ,

        Parameters
        ----------
        options: str
            Options to choose from separated by , (Required)
        """
        options = options.split(",")
        if len(options) < 2:
            return await ctx.send(
                "Please provide at least 2 options to choose from. Separate options with ,"
            )
        await ctx.send(truncate(random.choice(options).strip()))

    @commands.hybrid_command(brief="Show the profile of a user")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def profile(
        self,
        ctx: Context,
        user: Optional[User],
        download_avatar: Optional[bool] = False,
        server_avatar: Optional[bool] = False,
    ):
        """
        Show the profile of a user

        Parameters
        ----------
        user: Optional[User]
            User to show profile for. Defaults to self (Optional)
        download_avatar: Optional[bool]
            Download the avatar (Optional)
        server_avatar: Optional[bool]
            Use the server avatar instead of the user avatar (Optional)
        """
        if user is None:
            user = ctx.author

        if ctx.guild and server_avatar and user in ctx.guild.members:
            member = ctx.guild.get_member(user.id)
            if member:
                user = member
                avatar = user.display_avatar
            else:
                avatar = user.avatar
        else:
            avatar = user.avatar

        if download_avatar:
            avatar_bytes = await http_get(self.bot.web_client, avatar.url)
            avatar_bytes = BytesIO(avatar_bytes)
            filename = f"{user.name}{'.gif' if avatar.is_animated() else '.png'}"
            return await ctx.send(file=discord.File(avatar_bytes, filename=filename))

        embed = discord.Embed(
            title=f"{user.name}'s profile",
            color=user.accent_color if user.accent_color else user.color,
        )
        embed.set_thumbnail(url=avatar.url)
        embed.add_field(
            name="Created at", value=format_dt(user.created_at), inline=False
        )
        embed.add_field(name="Avatar URL", value=avatar.url, inline=False)
        if ctx.guild and user in ctx.guild.members:
            embed.add_field(
                name=f"Joined {ctx.guild.name} at",
                value=format_dt(user.joined_at),
                inline=False,
            )
            if len(user.roles) > 1:
                embed.add_field(
                    name="Roles",
                    value=", ".join([role.mention for role in user.roles[1:]]),
                    inline=False,
                )
            if user.premium_since:
                embed.add_field(
                    name="Boosting since",
                    value=format_dt(user.premium_since),
                    inline=False,
                )

        await ctx.send(embed=embed)

    @commands.hybrid_command(brief="Show the profile picture of a user")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def pfp(self, ctx: Context, user: User):
        """
        Show the profile picture of a user

        Parameters
        ----------
        user: User
            User to show profile picture for (Required)
        """
        await ctx.send(user.avatar.url)

    @commands.hybrid_command(brief="Show information about this server")
    @commands.guild_only()
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def serverinfo(self, ctx: Context, download_icon: Optional[bool] = False):
        """
        Show information about this server

        Parameters
        ----------
        download_icon: Optional[bool]
            Download the server icon (Optional)
        """
        guild = ctx.guild
        if download_icon:
            if not guild.icon:
                return await ctx.send("This server has no icon.")
            icon_bytes = await http_get(self.bot.web_client, guild.icon.url)
            icon_bytes = BytesIO(icon_bytes)
            filename = f"{guild.name}{'.gif' if guild.icon.is_animated() else '.png'}"
            return await ctx.send(file=discord.File(icon_bytes, filename=filename))

        embed = discord.Embed(title=f"{guild.name}'s info", color=guild.owner.color)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(
            name="Created at", value=format_dt(guild.created_at), inline=False
        )
        embed.add_field(name="Owner", value=guild.owner.mention, inline=False)
        embed.add_field(name="Members", value=guild.member_count, inline=False)
        if guild.premium_subscription_count:
            embed.add_field(
                name="Boosts", value=guild.premium_subscription_count, inline=False
            )
        if guild.premium_tier:
            embed.add_field(name="Boost Level", value=guild.premium_tier, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(brief="Search wiki")
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def wiki(self, ctx: Context, *, query: str):
        """
        Search wiki

        Parameters
        ----------
        query: str
            Query to search for (Required)
        """
        query = urllib.parse.quote(query)
        url = self.wiki_url.format(apikey=self.search_key, query=query)
        response = await http_get(self.bot.web_client, url, as_json=True)
        search_results = [SearchResult(item) for item in response["items"][:5]]
        view = SearchResultsView(ctx, search_results, 1)
        view.embed = view.create_embed(view.current_chunk)
        view.message = await ctx.send(embed=view.embed, view=view)


async def setup(bot):
    await bot.add_cog(MiscCog(bot))


def get_snowflake_data(string: str, bot: commands.Bot) -> Optional[dict]:
    result = {"type": "", "created": None, "str": ""}

    if string.isdigit():
        try:
            obj = discord.Object(int(string))
            if obj.created_at > datetime.utcnow().replace(tzinfo=timezone.utc):
                return None
            result["created"] = obj.created_at
            result["str"] = str(obj.id)
            return result
        except (OSError, OverflowError):
            return None

    if match := emoji_regex.search(string):
        result["type"] = "Emoji"
        result["created"] = discord.Object(int(match.group(3))).created_at
        result["str"] = match.group(2)
        # discord.get_emoji returns None
        for e in bot.emojis:
            if e.id == int(match.group(3)):
                result["str"] = string
                return result
        result["str"] = emoji_url(match.group(3), match.group(1) == "a")
        return result
    elif match := user_regex.search(string):
        result["type"] = "User"
        result["created"] = discord.Object(int(match.group(1))).created_at
        result["str"] = match.group(1)
        if user := bot.get_user(int(match.group(1))):
            result["str"] = f"{user.name}#{user.discriminator}"
        return result
    elif match := channel_regex.search(string):
        result["type"] = "Channel"
        result["created"] = discord.Object(int(match.group(1))).created_at
        result["str"] = match.group(1)
        if channel := bot.get_channel(int(match.group(1))):
            result["str"] = channel.name
        return result
    elif match := role_regex.search(string):
        result["type"] = "Role"
        result["created"] = discord.Object(int(match.group(1))).created_at
        result["str"] = match.group(1)
        return result
    return None
