import asyncio
from collections.abc import Awaitable, Callable
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
from rbb_bot.infrastructure.media.images import ImageTooLarge, crop_image, open_bounded
from rbb_bot.views.media import CropView

# Each source is downloaded and decoded in turn inside the one bot process; a
# message with dozens of links would tie a command up for minutes.
MAX_SOURCES = 5


def _encode(image: Image.Image, format: str | None, **params) -> bytes:
    with BytesIO() as buffer:
        image.save(buffer, format=format, **params)
        return buffer.getvalue()


# Pillow's `with image:` only closes the file pointer, not the decoded pixels, so
# the helpers below release intermediate images with explicit close() calls.
def _crop_to_bytes(image: Image.Image) -> bytes:
    cropped = crop_image(image)
    try:
        return _encode(cropped, str(image.format))
    finally:
        cropped.close()


def _transpose_to_bytes(image: Image.Image, method: Image.Transpose) -> bytes:
    transposed = image.transpose(method)
    try:
        return _encode(transposed, str(image.format))
    finally:
        transposed.close()


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
        sent: list[tuple[bytes, str]] = []

        async def crop_and_send(image: Image.Image, filename: str):
            try:
                data = await asyncio.to_thread(_crop_to_bytes, image)
            except Exception as e:
                await ctx.send(f"Could not crop image {filename}")
                await self.bot.send_error(ctx, e, comment="Error in crop_image()")
                return
            if await self.send_image(
                ctx, data, filename, comment="Error sending cropped image"
            ):
                sent.append((data, filename))

        processed = await self.process_sources(ctx, urls, crop_and_send)
        if processed != 1 or not sent:
            return
        prompt = "Would you like to crop more?"
        if not (await self.bot.get_confirmation(ctx, prompt)):
            return
        data, filename = sent[0]
        try:
            image = await asyncio.to_thread(open_bounded, data)
            view = CropView(ctx, filename, image)
            await view.send(discord.File(BytesIO(data), filename=filename))
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

        filename = url_to_filename(url)
        try:
            img = await self.get_image(url)
        except ImageTooLarge as e:
            return await self.send_too_large(ctx, filename, e)
        if not img:
            return await ctx.send("No image found")
        try:
            data = await asyncio.to_thread(
                _encode,
                img,
                img.format,
                save_all=getattr(img, "is_animated", False),
            )
        except BaseException:
            img.close()
            raise
        view = CropView(ctx, filename, img)
        await view.send(discord.File(BytesIO(data), filename=filename))

    async def get_image(self, url: str) -> Image.Image | None:
        """
        Download and decode one source, or None when it is not a usable image.

        `ImageTooLarge` propagates so the caller can tell the user which file was
        refused; other expected download/decode failures are skipped silently.
        """
        try:
            return await asyncio.to_thread(open_bounded, await http_get(url))
        except (InvalidURL, UnidentifiedImageError, TimeoutError, UnsafeDownload):
            return None
        except ImageTooLarge:
            raise
        except Exception as e:
            await self.bot.send_error(exc=e, comment="Error fetching image")
            return None

    async def send_too_large(self, ctx: Context, filename: str, error: ImageTooLarge):
        await ctx.send(f"Image {filename} is too large to process: {error.reason}")

    async def send_image(
        self, ctx: Context, data: bytes, filename: str, comment: str
    ) -> bool:
        try:
            await ctx.send(file=discord.File(BytesIO(data), filename=filename))
            return True
        except Exception as e:
            await ctx.send(f"Could not send image {filename}")
            await self.bot.send_error(ctx, e, comment=comment)
            return False

    async def process_sources(
        self,
        ctx: Context,
        urls: str | None,
        process: Callable[[Image.Image, str], Awaitable[None]],
    ) -> int:
        """
        Run `process` on each source image in turn and return how many decoded.

        Each image is fetched, processed and closed before the next is fetched, so
        a command holds at most one decoded source at a time.
        """
        sources = [url.strip() for url in (urls or "").split(" ") if url.strip()]
        sources.extend(attachment.url for attachment in ctx.message.attachments)
        if len(sources) > MAX_SOURCES:
            ignored = len(sources) - MAX_SOURCES
            await ctx.send(
                f"Only the first {MAX_SOURCES} images are processed; "
                f"ignored the other {ignored}."
            )
            sources = sources[:MAX_SOURCES]

        processed = 0
        refused = 0
        for url in sources:
            filename = url_to_filename(url)
            try:
                image = await self.get_image(url)
            except ImageTooLarge as e:
                refused += 1
                await self.send_too_large(ctx, filename, e)
                continue
            if image is None:
                continue
            processed += 1
            try:
                await process(image, filename)
            finally:
                image.close()
        if not processed and not refused:
            await ctx.send("No images found")
        return processed

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

        method = {
            90: Image.Transpose.ROTATE_90,
            180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_270,
        }[rotate_by]

        async def rotate_and_send(image: Image.Image, filename: str):
            try:
                data = await asyncio.to_thread(_transpose_to_bytes, image, method)
            except Exception as e:
                await ctx.send(f"Could not rotate image {filename}")
                await self.bot.send_error(ctx, e, comment="Error rotating")
                return
            await self.send_image(ctx, data, filename, comment="Error while sending")

        await self.process_sources(ctx, urls, rotate_and_send)

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

        method = (
            Image.Transpose.FLIP_LEFT_RIGHT
            if flip_direction == "h"
            else Image.Transpose.FLIP_TOP_BOTTOM
        )

        async def flip_and_send(image: Image.Image, filename: str):
            try:
                data = await asyncio.to_thread(_transpose_to_bytes, image, method)
            except Exception as e:
                await ctx.send(f"Could not flip image {filename}")
                await self.bot.send_error(ctx, e, comment="Error flipping")
                return
            await self.send_image(ctx, data, filename, comment="Error while sending")

        await self.process_sources(ctx, urls, flip_and_send)

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

        async def convert_and_send(image: Image.Image, filename: str):
            try:
                data = await asyncio.to_thread(
                    _encode, image, "PNG", save_all=True, optimize=True, background=0
                )
            except Exception as e:
                await ctx.send(f"Could not convert image {filename}")
                await self.bot.send_error(ctx, e, comment="Error converting")
                return
            output_name = Path(filename).stem + ".png"
            await self.send_image(ctx, data, output_name, comment="Error while sending")

        await self.process_sources(ctx, urls, convert_and_send)


async def setup(bot):
    await bot.add_cog(MediaCog(bot))
