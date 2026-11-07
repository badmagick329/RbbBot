import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from rbb_bot.memegifs.ffmpeg import concat_clips, create_image_clip

DATA_DIR = Path(__file__).parent / "data"


@dataclass
class Config:
    image_file: Path
    video_file: Path
    font_file: Path
    font_size: int
    rgb_color: tuple[int, int, int]


class ImageFrame:
    image: Image.Image
    image_draw: ImageDraw.Draw
    font: ImageFont.FreeTypeFont
    rgb_color: tuple[int, int, int]

    def __init__(self, config: Config) -> None:
        if not config.font_file.exists():
            raise FileNotFoundError("Font file not found")
        if not config.image_file.exists():
            raise FileNotFoundError("Image file not found")
        self.image = Image.open(config.image_file)
        self.image_draw = ImageDraw.Draw(self.image)
        self.font = ImageFont.truetype(str(config.font_file), config.font_size)
        self.rgb_color = config.rgb_color

    def draw_text(
        self, text: str, max_chars: int, max_lines: int, x: int, y: int
    ) -> Image.Image:
        text_lines = text_to_lines(text, max_chars)[:max_lines]
        y_offset = int(self.font.size * 1.25)
        for i, line in enumerate(text_lines):
            self.image_draw.text(
                (x, y + y_offset * i), line, font=self.font, fill=self.rgb_color
            )
        return self.image


class VideoGenerator:
    image_frame: ImageFrame
    video_file: Path

    def __init__(self, config: Config) -> None:
        self.image_frame = ImageFrame(config)
        self.video_file = config.video_file

    def image_with_text(
        self, text: str, max_chars: int, max_lines: int, x: int, y: int
    ) -> Image.Image:
        return self.image_frame.draw_text(text, max_chars, max_lines, x, y)

    async def generate_video(self, image: Image.Image, image_duration: int) -> bytes:
        """Render the source clip followed by `image` as a GIF.

        Each call gets its own temp directory so concurrent renders cannot
        collide and every intermediate is removed even when FFmpeg fails. The GIF
        is returned as bytes because nothing on disk outlives the directory.
        """
        with tempfile.TemporaryDirectory(prefix="rbb-meme-") as tmp:
            tmp_dir = Path(tmp)
            frame, clip = tmp_dir / "frame.png", tmp_dir / "frame.mp4"
            output = tmp_dir / "meme.gif"
            image.save(frame)
            width, height = image.size
            await create_image_clip(frame, clip, image_duration, width, height)
            await concat_clips(
                [self.video_file, clip], tmp_dir / "list.txt", output, width, height
            )
            return output.read_bytes()


class IreneTweeting(VideoGenerator):
    IMAGE_FILE = DATA_DIR / "irenetweet.png"
    VIDEO_FILE = DATA_DIR / "typing.mp4"
    FONT_FILE = DATA_DIR / "Roboto" / "Roboto-Bold.ttf"

    def __init__(self, font_size=24) -> None:
        assert DATA_DIR.exists(), "Data directory not found"
        config = Config(
            image_file=self.IMAGE_FILE,
            video_file=self.VIDEO_FILE,
            font_file=self.FONT_FILE,
            font_size=font_size,
            rgb_color=(40, 40, 40),
        )
        super().__init__(config)

    async def create(self, text: str) -> bytes:
        image = self.image_with_text(text, 38, 3, 120, 100)
        return await self.generate_video(image, 3)


class ElijahTerrific(VideoGenerator):
    IMAGE_FILE = DATA_DIR / "elijah.png"
    VIDEO_FILE = DATA_DIR / "elijah.mp4"
    FONT_FILE = DATA_DIR / "Roboto" / "Roboto-Bold.ttf"

    def __init__(self, font_size: int = 44) -> None:
        assert DATA_DIR.exists(), "Data directory not found"
        config = Config(
            image_file=self.IMAGE_FILE,
            video_file=self.VIDEO_FILE,
            font_file=self.FONT_FILE,
            font_size=font_size,
            rgb_color=(184, 97, 255),
        )
        super().__init__(config)

    async def create(self, text: str) -> bytes:
        image = self.image_with_text(text, 14, 4, 12, 20)
        return await self.generate_video(image, 5)


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
