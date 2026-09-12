import asyncio
from contextlib import closing
from io import BytesIO

import discord
from discord import ButtonStyle, Interaction
from discord.ext.commands import Context
from discord.ui import Button, View
from rbb_bot.infrastructure.media.images import normalize_image

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
        await interaction.response.defer()
        async with self.view.lock:
            if self.view.is_finished():
                return
            self.view.selected_size = self.crop_size
            self.view.update_size_buttons()
            await interaction.edit_original_response(view=self.view)


class CropButton(Button):
    def __init__(self, direction: str, *args, **kwargs):
        label = self.direction = direction
        super().__init__(style=ButtonStyle.blurple, label=label, *args, **kwargs)

    async def callback(self, interaction: Interaction):
        await interaction.response.defer()
        await self.view.crop(self.direction)


class CropView(View):
    MAX_CROPS = 10
    init_message = (
        "Select a crop size and then click a direction button to crop"
        "\nWidth:{width} Height:{height}"
    )

    def __init__(self, ctx: Context, filename: str, image, timeout: int = 60):
        self.ctx = ctx
        self.image = image
        self.message = None
        self.filename = filename
        self.lock = asyncio.Lock()
        self.crop_count = 0
        self.selected_size = SMALL
        self.size_buttons = list()
        super().__init__(timeout=timeout)
        self.create_buttons()

    async def send(self, attachment):
        # A timeout or first click must not run before Discord returns the message.
        async with self.lock:
            try:
                self.message = await self.ctx.send(
                    self.formatted_text, view=self, file=attachment
                )
            except Exception:
                self._release_image()
                raise

    async def crop(self, direction):
        """Serialize image edits and closing so an in-flight crop cannot reopen a finished view."""
        async with self.lock:
            if self.is_finished():
                return
            width, height = self.image.size
            if width < X_LARGE * 2 or height < X_LARGE * 2:
                await self._stop_view()
                return
            size = self.selected_size
            bounds = {
                TOP: (0, size, width, height),
                RIGHT: (0, 0, width - size, height),
                BOTTOM: (0, 0, width, height - size),
                LEFT: (size, 0, width, height),
            }
            with normalize_image(self.image) as normalized:
                new_image = normalized.crop(bounds[direction])
            new_image.format = self.image.format
            try:
                with BytesIO() as buffer:
                    new_image.save(buffer, format=new_image.format)
                    buffer.seek(0)
                    with closing(discord.File(buffer, filename=self.filename)) as file:
                        await self.message.edit(attachments=[file])
            except Exception:
                new_image.close()
                raise
            self.image.close()
            self.image = new_image
            self.crop_count += 1
            if self.crop_count == self.MAX_CROPS:
                await self._stop_view()
                return
            await self.message.edit(content=self.formatted_text, view=self)

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
                f"You can crop the image {self.MAX_CROPS - self.crop_count} more times"
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
        async with self.lock:
            await self._stop_view()

    def _release_image(self):
        self.stop()
        self.clear_items()
        if self.image is not None:
            self.image.close()
            self.image = None

    async def _stop_view(self):
        self._release_image()
        if self.message is not None:
            await self.message.edit(content=None, view=self)

    async def interaction_check(self, interaction: Interaction) -> bool:
        return (
            interaction.user == self.ctx.author
            and interaction.channel == self.ctx.channel
        )

    async def on_error(
        self, interaction: Interaction, error: Exception, item: Button
    ) -> None:
        self.ctx.bot.logger.error("Error in CropView", exc_info=error)
