import re

from discord import Embed
from discord.utils import format_dt

from rbb_bot.application.releases.contracts import ReleaseListing
from rbb_bot.utils.helpers import truncate
from rbb_bot.utils.views import ListView


class VideoList(ListView):
    def create_message(self, current_chunk: list[tuple[str, ReleaseListing]]) -> str:
        header = f"Page {self.current_page + 1} of {len(self.view_chunks)}\n"
        body = list()
        for chunk in current_chunk:
            video, release = chunk
            artist_name = truncate(release.artist, 30)
            title = truncate(release.title, 30)
            if release.release_time:
                date_or_time = format_dt(release.release_time, style="f")
            else:
                date_or_time = f"**{release.release_date}**"
            body.append(f"{date_or_time}\n{artist_name} - {title}\n{video}")
        return header + "\n".join(body)


class ReleasesView(ListView):
    YT_URL = re.compile(
        r"(?:https?://)?(?:www\.)?youtu(?:be\.com/watch\?v=|\.be/)([\w-]{11})"
    )

    def create_embed(self, releases: list[ReleaseListing]) -> Embed:
        def format_release_field(r: ReleaseListing) -> tuple[str, str]:
            release_time = (
                format_dt(r.release_time, "f")
                if r.release_time
                else r.release_date.strftime("%Y-%m-%d")
            )

            artist_name = truncate(r.artist, 80)

            title_and_album = ""
            if r.title == r.album_title:
                title_and_album = r.title
            else:
                if r.title:
                    title_and_album += r.title
                if r.album_title:
                    title_and_album += (
                        f" ({r.album_title})" if title_and_album else r.album_title
                    )

            title_and_album = truncate(title_and_album, 80)
            release_type = f"*[{r.release_type}]*" if r.release_type else ""
            value_ = f"`{artist_name}`\n{title_and_album}"
            if release_type:
                value_ += f"\n{release_type}"
            if r.urls:
                for url in r.urls[:4]:
                    if match := self.YT_URL.search(url):
                        value_ += f"\nhttps://youtu.be/{match.group(1)}"
                    else:
                        value_ += f"\n{url}"
            return release_time, value_

        embed = Embed(
            title=f"Page {self.current_page + 1} of {len(self.view_chunks)}",
            description="[Browse releases on the web](https://mgck.ink/kpop)",
        )
        header_name = f"{len(self.list_items)} {'releases' if len(self.list_items) > 1 else 'release'}"
        header_value = "Times displayed in your local timezone"
        embed.add_field(name=header_name, value=header_value, inline=False)
        for release in releases:
            name, value = format_release_field(release)
            value = f"{value}\n{'-' * 50}"
            embed.add_field(name=name, value=value, inline=False)
        embed.set_footer(text="Source: https://www.reddit.com/r/kpop")
        return embed
