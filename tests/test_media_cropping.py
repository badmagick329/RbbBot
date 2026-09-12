import pytest
from PIL import Image, ImageDraw

from rbb_bot.cogs.media_cog import crop_image, normalize_image


@pytest.mark.parametrize("mode", ["L", "P", "RGB", "RGBA", "LA"])
def test_cropping_accepts_grayscale_palette_and_color_images(mode):
    image = Image.new("RGB", (200, 200), "black")
    ImageDraw.Draw(image).rectangle((20, 20, 179, 179), fill="white")
    if mode == "P":
        image = image.quantize()
    else:
        image = image.convert(mode)
    result = crop_image(image)
    assert result.width > 0 and result.height > 0
    assert result.width <= image.width and result.height <= image.height


def test_palette_transparency_is_preserved_for_manual_cropping():
    image = Image.new("P", (200, 200))
    image.info["transparency"] = 0
    result = normalize_image(image)
    assert result.mode == "RGBA"
    assert result.getpixel((0, 0))[3] == 0
