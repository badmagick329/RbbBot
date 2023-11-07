import asyncio
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from rbb_bot.tweetmeme.consts import (FONT_FILE, IMAGE_FILE, TEMP_DIR,
                                      TYPING_FILE)
from rbb_bot.tweetmeme.ffmpeg import concat_clips, create_image_clip
from rbb_bot.tweetmeme.utils import remove_files


class TweetImage:
    image: Image.Image
    image_draw: ImageDraw.Draw
    font: ImageFont.FreeTypeFont
    rgb_color: tuple[int, int, int]
    MAX_LINES = 3

    def __init__(
        self,
        image_file: Path,
        font_file: Path,
        font_size: int = 24,
        rgb_color: tuple[int, int, int] = (40, 40, 40),
    ) -> None:
        if not font_file.exists():
            raise FileNotFoundError("Font file not found")
        if not image_file.exists():
            raise FileNotFoundError("Image file not found")
        self.image = Image.open(image_file)
        self.image_draw = ImageDraw.Draw(self.image)
        self.font = ImageFont.truetype(str(font_file), font_size)
        self.rgb_color = rgb_color

    def draw_text(self, text: str) -> Image.Image:
        text_lines = text_to_lines(text, 40)[: self.MAX_LINES]
        for i, line in enumerate(text_lines):
            self.image_draw.text(
                (120, 100 + 30 * i), line, font=self.font, fill=self.rgb_color
            )
        return self.image


class TweetMeme:
    tweet_image: TweetImage
    video_file: Path

    def __init__(self) -> None:
        image_file = IMAGE_FILE
        font_file = FONT_FILE
        video_file = TYPING_FILE
        self.tweet_image = TweetImage(image_file, font_file)
        self.video_file = video_file

    async def create_meme(
        self, text: str, image_duration: int = 3, clean_up: bool = True
    ) -> Path:
        image = self.tweet_image.draw_text(text)
        tmp_name = str(TEMP_DIR / f"tmp_{datetime.now().timestamp()}")
        tmp_image, tmp_video = f"{tmp_name}.png", f"{tmp_name}.mp4"
        list_file = f"{tmp_name}.txt"
        # final_video = f"{tmp_name}_final.mp4"
        output = f"{tmp_name}_final"
        image.save(tmp_image)
        width, height = image.size
        await create_image_clip(
            tmp_image, tmp_video, image_duration, width, height
        )
        final_name = await concat_clips(
            [str(self.video_file), tmp_video],list_file, output, width, height
        )
        if clean_up:
            remove_files([tmp_image, tmp_video])
        return TEMP_DIR / final_name


def text_to_lines(text: str, line_max: int = 40) -> list[str]:
    lines = list()
    line = ""
    words = text_to_words(text, line_max)
    while words:
        next_word = words.pop(0)
        new_len = len(line) + len(next_word) + 1
        if new_len > line_max and line:
            lines.append(line.strip())
            line = ""
        line += next_word + " "
    if line:
        lines.append(line.strip())
    return lines


def text_to_words(text: str, max_word: int) -> list[str]:
    words = list()
    for w in text.split():
        if len(w) > max_word:
            words.extend(split_word(w, max_word))
            continue
        words.append(w)
    return words


def split_word(word: str, max_word: int) -> list[str]:
    words = list()
    if len(word) > max_word:
        last_word = word
        while len(last_word) > max_word:
            words.append(last_word[:max_word])
            last_word = last_word[max_word:]
        if last_word != "":
            words.append(last_word)
    return words


def main():
    asyncio.run(run())


async def run():
    irene_meme = TweetMeme()
    video = await irene_meme.create_meme("ABC1ABC2ABC3ABC4ABC5ABC6ABC7ABC8 🤔")
    print(video)


if __name__ == "__main__":
    main()
