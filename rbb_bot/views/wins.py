import re

from discord import Embed

from rbb_bot.application.wins.latest import RecordedWin

PUBLIC_SITE = "https://kpopwins.info"
ARCHIVE_LINK = f"[Browse the wins archive]({PUBLIC_SITE}/wins)"


def display_text(value: str, limit: int) -> str:
    """Clip before escaping so truncation cannot leave an unfinished escape."""
    value = " ".join(value.split())
    value = value[: limit - 1] + "…" if len(value) > limit else value
    # Link labels need brackets/parentheses escaped too; neutralize mention-like
    # strings even when they do not currently contain a valid Discord snowflake.
    return re.sub(r"([\\`*_{}\[\]()<>|~])", r"\\\1", value).replace("@", "@\u200b")


def wins_embed(
    wins: tuple[RecordedWin, ...] = (),
    *,
    artist: str | None = None,
    unavailable: bool = False,
) -> Embed:
    title = "Latest recorded wins"
    if artist is not None:
        title += f" for {display_text(artist, 80)}"
    description = ARCHIVE_LINK
    if unavailable:
        description = (
            "Results are temporarily unavailable. Please try again later.\n\n"
            + ARCHIVE_LINK
        )
    elif not wins:
        description = "No recorded wins matched.\n\n" + ARCHIVE_LINK
    embed = Embed(title=title, url=PUBLIC_SITE + "/wins", description=description)
    for win in wins[:5]:
        embed.add_field(
            name=f"{win.date.isoformat()} · {display_text(win.show, 80)}",
            value=(
                f"[{display_text(win.artist, 150)}]({PUBLIC_SITE}/artists/{win.artist_slug})"
                f"\n[{display_text(win.song, 150)}]({PUBLIC_SITE}/songs/{win.song_id})"
            ),
            inline=False,
        )
    return embed
