from io import BytesIO
from pathlib import Path
from typing import Literal, Optional

import discord
from aiohttp.client_exceptions import InvalidURL
from discord.ext import commands
from discord.ext.commands import Cog, Context
from PIL import Image, UnidentifiedImageError
from rbb_bot.utils.exceptions import TimeoutError
from rbb_bot.infrastructure.http.public_download import UnsafeDownload
from rbb_bot.utils.helpers import http_get, url_to_filename
from rbb_bot.infrastructure.media.images import crop_image
from rbb_bot.views.media import CropView


class MediaCog(Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.logger.debug("MediaCog loaded!")

    async def cog_unload(self):
        self.bot.logger.debug("MediaCog unloaded!")

    @commands.hybrid_group(
        brief="Crop solid lines around images", invoke_without_command=True
    )
    async def crop(self, ctx: Context, *, urls: Optional[str] = ""):
        """
        Crop solid lines around images. Or manually adjust crop for an image

        Example:
        {prefix}crop [urls and/or attachments] or {prefix}crop images [urls and/or attachments]
        {prefix}crop adjust [url or attachment]
        """
        if urls or ctx.message.attachments:
            await ctx.invoke(self.crop_images, urls=urls)
        else:
            await ctx.send_help(ctx.command)

    @crop.command(name="images", brief="Crop solid lines around images")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def crop_images(self, ctx: Context, *, urls: Optional[str] = ""):
        """
        Crop solid lines around images

        Example:
        {prefix}crop images [urls and/or attachments]

        Parameters
        ----------
        urls : str
            The urls of images or attachments (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        images_and_names = await self.get_images_and_names(ctx, urls)
        if not images_and_names:
            return await ctx.send("No images found")
        sent_message = None
        image_bytes = None
        for image, filename in images_and_names:
            try:
                new_image = crop_image(image)
            except Exception as e:
                await ctx.send(f"Could not crop image {filename}")
                await self.bot.send_error(ctx, e, comment="Error in crop_image()")
                continue
            arr = BytesIO()
            new_image.save(arr, format=str(image.format))
            arr.seek(0)
            try:
                image_file = discord.File(arr, filename=filename)
                sent_message = await ctx.send(file=image_file)
                if len(images_and_names) == 1:
                    image_bytes = arr
            except Exception as e:
                await ctx.send(f"Could not send image {filename}")
                await self.bot.send_error(
                    ctx,
                    e,
                    comment="Error sending cropped image",
                )
        if len(images_and_names) != 1 or sent_message is None:
            return
        prompt = "Would you like to crop more?"
        if not (await self.bot.get_confirmation(ctx, prompt)):
            return
        try:
            image_bytes.seek(0)
            image = Image.open(image_bytes)
            image_bytes.seek(0)
            filename = images_and_names[0][1]
            discord_file = discord.File(image_bytes, filename=filename)
            view = CropView(ctx, filename, image)
            await view.send(discord_file)
        except Exception as e:
            self.bot.logger.error("Error on followup crop", exc_info=e)

    @crop.command(name="adjust", brief="Make adjustments to a cropped image")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def crop_adjust(self, ctx: Context, url: Optional[str] = ""):
        """
        Make adjustments to a cropped image

        Parameters
        ----------
        url : str
            The url of an image (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not url:
            if ctx.message.attachments:
                url = ctx.message.attachments[0].url
            else:
                return await ctx.send("No image source found")

        img = await self.get_image(url)
        if not img:
            return await ctx.send("No image found")
        filename = url_to_filename(url)
        image_bytes = BytesIO()
        img.save(
            image_bytes, format=img.format, save_all=getattr(img, "is_animated", False)
        )
        view = CropView(ctx, filename, img)
        image_bytes.seek(0)
        discord_file = discord.File(image_bytes, filename=filename)
        await view.send(discord_file)

    async def get_image(self, url: str) -> Image.Image | None:
        try:
            img = Image.open(BytesIO(await http_get(url)))
            img.load()
            return img
        except (InvalidURL, UnidentifiedImageError, TimeoutError, UnsafeDownload):
            return None
        except Exception as e:
            await self.bot.send_error(exc=e, comment="Error fetching image")
            return None

    @commands.hybrid_group(name="image", brief="Rotate or flip images")
    async def edit_image(self, ctx: Context):
        """
        Rotate or flip images

        Example:
        {prefix}image rotate [urls or attachments]
        {prefix}image flip [urls or attachments]
        """
        await ctx.send_help(ctx.command)

    @edit_image.command(name="rotate", brief="Rotate images counter-clockwise")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def rotate_image(
        self,
        ctx: Context,
        rotate_by: Literal[90, 180, 270],
        *,
        urls: Optional[str] = "",
    ):
        """
        Rotate images counter-clockwise

        Parameters
        ----------
        rotate_by : List
            The number of degrees to rotate by counter-clockwise (Required)
        urls : str
            The urls of images or attachments (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not rotate_by:
            return await ctx.send("No rotation amount specified")
        if not urls and not ctx.message.attachments:
            return await ctx.send("No image source found")
        if rotate_by not in [90, 180, 270]:
            return await ctx.send("Invalid rotation amount")

        if rotate_by == 90:
            rotate_by = Image.ROTATE_90
        elif rotate_by == 180:
            rotate_by = Image.ROTATE_180
        elif rotate_by == 270:
            rotate_by = Image.ROTATE_270

        images_and_names = await self.get_images_and_names(ctx, urls, check_ig=True)

        if not images_and_names:
            return await ctx.send("No images found")

        for image, filename in images_and_names:
            try:
                new_image = image.transpose(rotate_by)
            except Exception as e:
                await ctx.send(f"Could not rotate image {filename}")
                await self.bot.send_error(ctx, e, comment="Error rotating")
                continue
            arr = BytesIO()
            new_image.save(arr, format=str(image.format))
            arr.seek(0)
            try:
                await ctx.send(file=discord.File(arr, filename=filename))
            except Exception as e:
                await ctx.send(f"Could not send image {filename}")
                await self.bot.send_error(ctx, e, comment="Error while sending")

    @edit_image.command(name="flip", brief="Flip images horizontally or vertically")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def flip_image(
        self,
        ctx: Context,
        flip_direction: Literal["h", "v"],
        *,
        urls: Optional[str] = "",
    ):
        """
        Flip images horizontally or vertically

        Parameters
        ----------
        flip_direction : List
            The direction to flip by (h or v) (Required)
        urls : str
            The urls of images or attachments (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()
        if not flip_direction:
            return await ctx.send("No flip direction specified")
        if not urls and not ctx.message.attachments:
            return await ctx.send("No image source found")

        images_and_names = await self.get_images_and_names(ctx, urls, check_ig=True)

        if not images_and_names:
            return await ctx.send("No images found")

        for image, filename in images_and_names:
            try:
                new_image = image.transpose(
                    Image.FLIP_LEFT_RIGHT
                    if flip_direction == "h"
                    else Image.FLIP_TOP_BOTTOM
                )
            except Exception as e:
                await ctx.send(f"Could not flip image {filename}")
                await self.bot.send_error(ctx, e, comment="Error flipping")
                continue
            arr = BytesIO()
            new_image.save(arr, format=str(image.format))
            arr.seek(0)
            try:
                await ctx.send(file=discord.File(arr, filename=filename))
            except Exception as e:
                await ctx.send(f"Could not send image {filename}")
                await self.bot.send_error(ctx, e, comment="Error while sending")

    @edit_image.command(name="webp", brief="Convert images from webp to png")
    @commands.cooldown(2, 5, commands.BucketType.user)
    async def convert_webp(
        self,
        ctx: Context,
        *,
        urls: Optional[str] = "",
    ):
        """
        Convert images from webp to png

        Parameters
        ----------
        urls : str
            The urls of images or attachments (Required)
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if not urls and not ctx.message.attachments:
            return await ctx.send("No image source found")

        images_and_names = await self.get_images_and_names(ctx, urls, check_ig=True)

        if not images_and_names:
            return await ctx.send("No images found")

        for image, filename in images_and_names:
            arr = BytesIO()
            output_name = Path(filename).stem + ".png"
            image.save(arr, format="PNG", save_all=True, optimize=True, background=0)
            arr.seek(0)
            discord_file = discord.File(arr, filename=output_name)
            try:
                await ctx.send(file=discord_file)
            except Exception as e:
                await ctx.send(f"Could not send image {filename}")
                await self.bot.send_error(ctx, e, comment="Error while sending")
                continue

    async def get_images_and_names(
        self, ctx: Context, urls: str | None, check_ig=False
    ) -> list[tuple[Image.Image, str]]:
        """
        Get images and their filenames from urls or attachments
        """

        if not urls:
            image_urls = []
        else:
            image_urls = [url.strip() for url in urls.split(" ") if url.strip()]
        images_and_names = list()

        image_urls.extend([attachment.url for attachment in ctx.message.attachments])

        for url in image_urls:
            img = await self.get_image(url)
            if not img:
                continue
            images_and_names.append((img, url_to_filename(url)))

        return images_and_names


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
