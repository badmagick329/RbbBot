from dataclasses import dataclass
from pathlib import Path

DISCORD_MAX_MESSAGE = 2000
EMBED_MAX_TITLE = 255
EMBED_MAX_DESC = 4096
DISCORD_MAX_FILE_SIZE = 8 * 1024 * 1024
BOT_MAX_PREFIX = 10


@dataclass
class BotEmojis:
    TICK = "\N{WHITE HEAVY CHECK MARK}"
    CROSS = "\N{CROSS MARK}"
    DOWN_ARROW = "\N{DOWNWARDS BLACK ARROW}"
    TEXT = "\N{PAGE FACING UP}"
    IRENE_TIME = "<a:irenetime:766755195451211818>"
    IRENE_WARNING = "<a:irenewarning:1005144902352515092>"
    IRENE_TIME_URL = "https://cdn.discordapp.com/emojis/766755195451211818.gif"
    POINT_LEFT = "<:leopointleft:1040768669606748160>"
    POINT_RIGHT = "<:leopointright:1040768783515660329>"


@dataclass
class FilePaths:
    WORDS_FILE = Path(__file__).parent.parent / "data" / "hangman_words.txt"
    COLORS_FILE = Path(__file__).parent.parent / "data" / "colors.json"
    CACHE_DIR = Path(__file__).parent.parent / "data" / "media_cache"
    LOG_FILE = Path(__file__).parent.parent / "data" / "rbb_bot.log"
