from discord import Embed
from rbb_bot.utils.views import ListView


class ColorsList(ListView):
    def create_embed(self, colors: list[tuple[str, str]]) -> Embed:
        embed = Embed(title=f"Page {self.current_page + 1} of {len(self.view_chunks)}")
        for color in colors:
            name, hex_code = color
            embed.add_field(name=name, value=hex_code, inline=True)
        embed.set_footer(text=f"Source: https://htmlcolorcodes.com/color-names/")
        return embed
