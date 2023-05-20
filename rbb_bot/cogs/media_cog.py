from io import BytesIO
from pathlib import Path
from typing import Literal, Optional

import discord
import numpy as np
from aiohttp.client_exceptions import InvalidURL
from discord import ButtonStyle, Interaction
from discord.ext import commands
from discord.ext.commands import Cog, Context
from discord.ui import Button, View
from PIL import Image, UnidentifiedImageError
from utils.exceptions import TimeoutError
from utils.helpers import http_get, url_to_filename
from utils.sns import InstagramFetcher, Sns

from rbb_bot.utils.decorators import log_command

SMALL = 5
MEDIUM = 10
LARGE = 25
X_LARGE = 50
XX_LARGE = 100

LEFT = ".. from the left"
RIGHT = ".. from the right"
TOP = ".. from the top"
BOTTOM = ".. from the bottom"


class CropSizeButton(Button):
    def __init__(self, selected: bool, size: int, *args, **kwargs):
        label = f"Crop by {size} pixels.." if selected else size
        self.selected = selected
        self.crop_size = size
        style = ButtonStyle.green if selected else ButtonStyle.grey
        super().__init__(style=style, label=label, *args, **kwargs)

    async def callback(self, interaction: Interaction):
        if self.view is None:
            return
        self.view.selected_size = self.crop_size
        self.view.update_size_buttons()
        await interaction.response.edit_message(view=self.view)


class CropButton(Button):
    def __init__(self, direction: str, *args, **kwargs):
        label = self.direction = direction
        super().__init__(style=ButtonStyle.blurple, label=label, *args, **kwargs)

    async def callback(self, interaction: Interaction):
        await interaction.response.defer()
        if not self.view.listening:
            return
        await self.adjust_image(interaction, self.view.image)

    async def adjust_image(self, interaction: Interaction, image: Image):
        self.view.listening = False
        image_data = np.asarray(image)
        width, height = image.size
        if width < X_LARGE * 2 or height < X_LARGE * 2:
            await self.view.stop_view()
            return
        size = self.view.selected_size
        if self.direction == TOP:
            image_data = image_data[size:, :, :]
        if self.direction == RIGHT:
            image_data = image_data[:, :-size, :]
        if self.direction == BOTTOM:
            image_data = image_data[:-size, :, :]
        if self.direction == LEFT:
            image_data = image_data[:, size:, :]
        new_image = Image.fromarray(image_data)
        buffer = BytesIO()
        new_image.save(buffer, format=str(self.view.image.format))
        buffer.seek(0)
        await self.view.message.edit(
            attachments=[discord.File(buffer, filename=self.view.filename)]
        )
        buffer.seek(0)
        self.view.image = Image.open(BytesIO(buffer.read()))

        self.view.crop_count += 1
        if self.view.crop_count == self.view.MAX_CROPS:
            await self.view.stop_view()
            return
        await self.view.message.edit(content=self.view.formatted_text, view=self.view)
        self.view.listening = True


class CropView(View):
    MAX_CROPS = 10
    init_message = (
        "Select a crop size and then click a direction button to crop"
        "\nWidth:{width} Height:{height}"
    )

    def __init__(self, ctx: Context, filename: str, timeout: int = 60):
        self.ctx = ctx
        self.image = None
        self.message = None
        self.filename = filename
        self.listening = True
        self.crop_count = 0
        self.selected_size = SMALL
        self.size_buttons = list()
        super().__init__()
        self.create_buttons()

    def update_size_buttons(self):
        for button in self.size_buttons:
            button.selected = button.crop_size == self.selected_size
            button.style = ButtonStyle.green if button.selected else ButtonStyle.grey
            button.label = (
                f"Crop by {button.crop_size} pixels.."
                if button.selected
                else button.crop_size
            )

    def create_buttons(self):
        self.size_buttons = [
            CropSizeButton(self.selected_size == SMALL, SMALL),
            CropSizeButton(self.selected_size == MEDIUM, MEDIUM),
            CropSizeButton(self.selected_size == LARGE, LARGE),
            CropSizeButton(self.selected_size == X_LARGE, X_LARGE),
            CropSizeButton(self.selected_size == XX_LARGE, XX_LARGE),
        ]
        for button in self.size_buttons:
            self.add_item(button)

        self.add_item(CropButton(LEFT, row=1))
        self.add_item(CropButton(TOP, row=1))
        self.add_item(CropButton(RIGHT, row=1))
        self.add_item(CropButton(BOTTOM, row=1))

    @property
    def formatted_text(self):
        if self.crop_count == 0:
            crop_text = f"You can crop the image {self.MAX_CROPS} times"
        else:
            crop_text = (
                f"You can crop the image {self.MAX_CROPS-self.crop_count} more times"
            )
        return (
            f"{self.init_message.format(width=self.image.width, height=self.image.height)}\n"
            f"{crop_text}"
        )

    @discord.ui.button(label="Close", style=ButtonStyle.red, row=2)
    async def close(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        await self.stop_view()

    async def on_timeout(self):
        await self.stop_view()

    async def stop_view(self):
        while self.children:
            self.remove_item(self.children[0])
        await self.message.edit(content=None, view=self)
        self.image = None
        self.stop()

    async def interaction_check(self, interaction: Interaction) -> bool:
        return (
            interaction.user == self.ctx.author
            and interaction.channel == self.ctx.channel
        )

    async def on_error(
        self, interaction: Interaction, error: Exception, item: Button
    ) -> None:
        self.ctx.bot.logger.error("Error in CropView", exc_info=error)


class MediaCog(Cog):
    def __init__(self, bot):
        self.bot = bot
        instagram_fetcher = InstagramFetcher(
            self.bot.config.ig_headers,
            self.bot.creds.ig_cookies,
            logger=self.bot.logger,
        )
        self.sns_instagram = Sns(instagram_fetcher, timestamped_urls=True)

    async def cog_load(self):
        self.bot.logger.debug("MediaCog loaded!")

    async def cog_unload(self):
        await self.sns_instagram.fetcher.web_client.close()
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
    @log_command(command_name="crop images")
    async def crop_images(self, ctx: Context, *, urls: Optional[str] = ""):
        """
        Crop solid lines around images

        Example:
        {prefix}crop images [urls and/or attachments]

        Parameters
        ----------
        urls : str
            The urls of images, instagram post or attachments (Required)
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
                await self.bot.send_error(
                    ctx, e, include_attachments=True, comment="Error in crop_image()"
                )
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
                self.bot.send_error(
                    ctx,
                    e,
                    include_attachments=True,
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
            init_text = CropView.init_message.format(
                width=image.size[0], height=image.size[1]
            )
            image_bytes.seek(0)
            filename = images_and_names[0][1]
            discord_file = discord.File(image_bytes, filename=filename)
            view = CropView(ctx, filename)
            view.message = await ctx.send(init_text, view=view, file=discord_file)
            view.image = image
        except Exception as e:
            self.bot.logger.error(exc_info=e, comment="Error on followup crop")

    @crop.command(name="adjust", brief="Make adjustments to a cropped image")
    @commands.cooldown(2, 5, commands.BucketType.user)
    @log_command(command_name="crop adjust")
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
        image_bytes = BytesIO(await http_get(self.bot.web_client, url))
        image = Image.open(image_bytes)
        init_text = CropView.init_message.format(
            width=image.size[0], height=image.size[1]
        )
        view = CropView(ctx, filename)
        image_bytes.seek(0)
        discord_file = discord.File(image_bytes, filename=filename)
        view.message = await ctx.send(init_text, view=view, file=discord_file)
        view.image = image

    async def get_image(self, url: str) -> Image.Image | None:
        try:
            img = Image.open(BytesIO(await http_get(self.bot.web_client, url)))
            return img
        except (InvalidURL, UnidentifiedImageError, TimeoutError):
            return None
        except Exception as e:
            await self.bot.send_error(exc=e, comment=f"Error in get_image({url})")
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
    @log_command(command_name="edit image rotate")
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
            The urls of images, instagram post or attachments (Required)
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
                await self.bot.send_error(
                    ctx, e, include_attachments=True, comment="Error rotating"
                )
                continue
            arr = BytesIO()
            new_image.save(arr, format=str(image.format))
            arr.seek(0)
            try:
                await ctx.send(file=discord.File(arr, filename=filename))
            except Exception as e:
                await ctx.send(f"Could not send image {filename}")
                await self.bot.send_error(
                    ctx, e, include_attachments=True, comment="Error while sending"
                )

    @edit_image.command(name="flip", brief="Flip images horizontally or vertically")
    @commands.cooldown(2, 5, commands.BucketType.user)
    @log_command(command_name="edit image flip")
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
            The urls of images, instagram post or attachments (Required)
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
                await self.bot.send_error(
                    ctx, e, include_attachments=True, comment="Error flipping"
                )
                continue
            arr = BytesIO()
            new_image.save(arr, format=str(image.format))
            arr.seek(0)
            try:
                await ctx.send(file=discord.File(arr, filename=filename))
            except Exception as e:
                await ctx.send(f"Could not send image {filename}")
                await self.bot.send_error(
                    ctx, e, include_attachments=True, comment="Error while sending"
                )

    @edit_image.command(name="webp", brief="Convert images from webp to png")
    @commands.cooldown(2, 5, commands.BucketType.user)
    @log_command(command_name="convert webp")
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
            The urls of images, instagram post or an attachment (Required)
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
                await self.bot.send_error(
                    ctx, e, include_attachments=True, comment="Error while sending"
                )
                continue

    async def get_images_and_names(
        self, ctx: Context, urls: str, check_ig=False
    ) -> list[tuple[Image.Image, str]]:
        """
        Get images and their filenames from urls or attachments
        """
        image_urls = [url.strip() for url in urls.split(" ") if url.strip()]
        instagram_urls = list()
        images_and_names = list()

        if check_ig and (ig_urls := self.sns_instagram.fetcher.find_urls(urls)):
            instagram_urls.extend(ig_urls)
            fetch_result = await self.sns_instagram.fetch(ig_urls[0])
            if fetch_result.post_data:
                post_data = fetch_result.post_data
                image_urls.extend(post_data.urls)
                for post_media in post_data.media_list:
                    image = Image.open(post_media.bytes_io)
                    images_and_names.append((image, post_media.filename))
                for file_path in post_data.file_path_list:
                    try:
                        image = Image.open(file_path)
                    except UnidentifiedImageError:
                        continue
                    images_and_names.append((image, file_path))

        image_urls.extend([attachment.url for attachment in ctx.message.attachments])
        image_urls = [url for url in image_urls if url not in instagram_urls]

        for url in image_urls:
            img = await self.get_image(url)
            if not img:
                continue
            images_and_names.append((img, url_to_filename(url)))

        return images_and_names


async def setup(bot):
    await bot.add_cog(MediaCog(bot))


def crop_image(img: Image.Image, threshold: int = 10) -> Image.Image:
    """
    Take an image and crop the solid line borders around it

    Parameters
    ----------
    img : Image.Image
        The image to crop
    threshold : int
        The threshold for considering 2 pixels to be the same color
    """
    img_data = np.asarray(img)
    mid_height = img_data.shape[0] // 2
    height = img_data.shape[0]
    width = img_data.shape[1]

    top_y = 0
    bottom_y = height
    threshold = 15
    GRAD_STEP = 20

    def is_close(pixel1: list[int], pixel2: list[int], threshold: int):
        for i in range(3):
            if abs(pixel1[i] - pixel2[i]) > threshold:
                return False
        return True

    def calc_top_y(img_data: np.ndarray, mid_height: int, additional_crop: int = 5):
        """
        Additional crop is to account for the noise in images esp jpg
        """
        top_y = 0
        for y in range(mid_height, 0, -1):
            top_y = y + additional_crop
            r_std = np.std(img_data[y, :, 0])
            g_std = np.std(img_data[y, :, 1])
            b_std = np.std(img_data[y, :, 2])
            if r_std < threshold and g_std < threshold and b_std < threshold:
                break
        return top_y

    def calc_bottom_y(img_data: np.ndarray, mid_height: int, additional_crop: int = 5):
        bottom_y = height
        for y in range(mid_height, height):
            bottom_y = y - additional_crop
            r_std = np.std(img_data[y, :, 0])
            g_std = np.std(img_data[y, :, 1])
            b_std = np.std(img_data[y, :, 2])
            if r_std < threshold and g_std < threshold and b_std < threshold:
                break
        return bottom_y

    def calc_left_x(
        img_data: np.ndarray, width: int, step: int, additional_crop: int = 5
    ):
        left_x = width - 2
        for y in range(top_y, bottom_y, step):
            x = 0
            while x < width - 2 and x < left_x:
                # if not np.allclose(img_data[y, 0, :], img_data[y, x+1, :], atol=threshold):
                if not is_close(
                    img_data[y, 0].tolist(), img_data[y, x + 1].tolist(), threshold
                ):
                    left_x = x
                    break
                x += 1
        return 0 if left_x == width - 2 else left_x + additional_crop

    def calc_right_x(
        img_data: np.ndarray, width: int, step: int, additional_crop: int = 5
    ):
        right_x = 0
        for y in range(top_y, bottom_y, step):
            x = width - 1
            while x > 2 and x > right_x:
                # if not np.allclose(img_data[y, width-1, :], img_data[y, x-1, :], atol=threshold):
                if not is_close(
                    img_data[y, width - 1].tolist(),
                    img_data[y, x - 1].tolist(),
                    threshold,
                ):
                    right_x = x
                    break
                x -= 1
        return width - 1 if right_x == 0 else right_x - additional_crop

    top_y = calc_top_y(img_data, mid_height)
    bottom_y = calc_bottom_y(img_data, mid_height)
    left_x = calc_left_x(img_data, width, GRAD_STEP)
    right_x = calc_right_x(img_data, width, GRAD_STEP)
    return Image.fromarray(img_data[top_y:bottom_y, left_x:right_x, :])
