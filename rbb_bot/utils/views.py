from dataclasses import dataclass
from typing import List

import discord
from discord import Interaction, ButtonStyle, Embed
from discord.ext import menus
from discord.ext.commands import Context
from discord.ui import Button, View
from settings.const import BotEmojis


class ConfirmView(View):
    def __init__(self, ctx: Context, timeout: int = 60):
        """
        A view that asks the user to confirm an action.

        Parameters
        ----------
        ctx: Context
            The context of the command.
        timeout: int
            The time in seconds to wait for a response.
        """
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.message = None
        self.confirmed = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        return (
            interaction.user == self.ctx.author
            and interaction.channel == self.ctx.channel
        )

    async def on_timeout(self) -> None:
        await self.message.edit(content="Timed out.")
        await self.stop_view()

    async def on_error(
        self, interaction: Interaction, error: Exception, item: Button
    ) -> None:
        await self.ctx.bot.send_error(
            exc=error, ctx=self.ctx, comment="Error in ConfirmView", stack_info=True
        )
        await interaction.response.send_message("An error occurred 😕")

    @discord.ui.button(label="Yes", style=ButtonStyle.green)
    async def yes(self, interaction: Interaction, button: Button):
        self.confirmed = True
        await interaction.response.edit_message(view=self)
        await self.stop_view()

    @discord.ui.button(label="No", style=ButtonStyle.red)
    async def no(self, interaction: Interaction, button: Button):
        self.confirmed = False
        await interaction.response.edit_message(view=self)
        await self.stop_view()

    async def stop_view(self):
        yes_button = discord.utils.get(self.children, label="Yes")
        no_button = discord.utils.get(self.children, label="No")

        remove, disable = (
            (no_button, yes_button) if self.confirmed else (yes_button, no_button)
        )
        self.remove_item(remove)
        disable.disabled = True

        await self.message.edit(view=self)
        self.stop()


class JumpButton(Button):
    def __init__(self, jump_amount: int):
        if jump_amount == 1 or jump_amount == -1:
            label = "Next" if jump_amount == 1 else "Previous"
            emoji = None
        else:
            emoji = BotEmojis.POINT_LEFT if jump_amount < 0 else BotEmojis.POINT_RIGHT
            label = abs(jump_amount)
        self.jump_amount = jump_amount
        if label:
            super().__init__(style=ButtonStyle.grey, label=label, emoji=emoji)
        else:
            super().__init__(style=ButtonStyle.grey, emoji=emoji)

    async def callback(self, interaction: Interaction):
        current_page = self.view.current_page + self.jump_amount
        if current_page < 0:
            current_page = 0
        elif current_page > len(self.view.view_chunks) - 1:
            current_page = len(self.view.view_chunks) - 1
        self.view.current_page = current_page
        self.view.current_chunk = self.view.view_chunks[self.view.current_page]
        await interaction.response.edit_message(
            content=self.view.create_message(self.view.current_chunk),
            embed=self.view.create_embed(self.view.current_chunk),
            view=self.view,
        )


class ListView(View):
    def __init__(self, ctx: Context, list_items: List, chunk_size=5, timeout=60.0):
        """
        A simple List View to display a list of items in a paginated manner

        Parameters
        ----------
        ctx: Context
            The context of the command

        list_items: List
            The list of items to display

        chunk_size: int
            The number of items to display per page

        """
        self.list_items = list_items
        self.chunk_size = chunk_size
        self.view_chunks = [
            self.list_items[i : i + self.chunk_size]
            for i in range(0, len(self.list_items), self.chunk_size)
        ]
        self.current_page = 0
        self.current_chunk = self.view_chunks[self.current_page]
        self.ctx = ctx
        self.message = None
        super().__init__(timeout=timeout)
        if len(self.view_chunks) == 1:
            while self.children:
                self.remove_item(self.children[0])
        else:
            jump_amount = int(len(self.view_chunks) / 3)
            if jump_amount > 2:
                self.add_item(JumpButton(-jump_amount))
                self.add_item(JumpButton(-1))
                self.add_item(JumpButton(1))
                self.add_item(JumpButton(jump_amount))
            else:
                self.add_item(JumpButton(-1))
                self.add_item(JumpButton(1))

    def create_embed(self, current_chunk) -> Embed:
        """
        Override this method to create an embed for the current chunk of items

        Either this method or create_message must return something to display based on the current chunk

        Remember to call this and set the embed on the initial message
        """
        pass

    def create_message(self, current_chunk) -> str:
        """
        Override this method to create a message for the current chunk of items

        Either this method or create_embed must return something to display based on the current chunk

        Remember to call this and set the content on the initial message
        """
        pass

    @discord.ui.button(label="Close", style=ButtonStyle.red, row=1)
    async def close(self, interaction: Interaction, button: Button):
        while self.children:
            self.remove_item(self.children[0])
        await interaction.response.edit_message(
            content=self.create_message(self.current_chunk), view=self
        )

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.ctx.author.id

    async def on_timeout(self) -> None:
        while self.children:
            self.remove_item(self.children[0])
        await self.message.edit(
            content=self.create_message(self.current_chunk), view=self
        )

    async def on_error(
        self, interaction: Interaction, error: Exception, item: Button
    ) -> None:
        await self.ctx.bot.send_error(
            exc=error, ctx=self.ctx, comment="Error in ListView", stack_info=True
        )
        await interaction.response.send_message("An error occurred 😕")


class Confirm(menus.Menu):
    def __init__(self, msg):
        super().__init__(timeout=60.0, clear_reactions_after=True)
        self.msg = msg
        self.result = None

    async def send_initial_message(self, ctx, channel):
        return self.msg

    @menus.button(BotEmojis.DOWN_ARROW)
    async def do_confirm(self, payload):
        self.result = True
        self.stop()

    # @menus.button('\N{CROSS MARK}')
    # async def do_deny(self, payload):
    #     self.result = False
    #     self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


class SnsMenu(menus.Menu):
    def __init__(self, msg):
        super().__init__(timeout=60.0, clear_reactions_after=True)
        self.msg = msg
        self.result = None

    async def send_initial_message(self, ctx, channel):
        return self.msg

    @menus.button(BotEmojis.DOWN_ARROW)
    async def no_text(self, payload):
        self.result = "no_text"
        self.stop()

    @menus.button(BotEmojis.TEXT)
    async def text(self, payload):
        self.result = "text"
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


@dataclass
class SearchResult:
    title: str
    link: str
    description: str
    image_url: str = None

    def __init__(self, item: dict):
        self.title = item["title"]
        self.link = item["link"]
        self.description = item["snippet"]
        if "pagemap" in item:
            try:
                for tag in item["pagemap"]["metatags"]:
                    if "og:image" in tag:
                        self.image_url = tag["og:image"]
                        break
            except KeyError:
                pass


class SearchResultsView(ListView):
    def create_embed(self, results: List[SearchResult]) -> Embed:
        embed = Embed(
            title=f"Results page {self.current_page + 1} of {len(self.view_chunks)}"
        )
        for result in results:
            embed.add_field(name=result.title, value=result.description, inline=False)
            embed.add_field(name="Link", value=result.link, inline=False)
            if result.image_url:
                embed.set_image(url=result.image_url)
        return embed
