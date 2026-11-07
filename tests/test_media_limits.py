import asyncio
import threading
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from PIL import Image, ImageDraw, ImageFile

from rbb_bot.cogs import media_cog
from rbb_bot.cogs.media_cog import MAX_SOURCES, MediaCog
from rbb_bot.infrastructure.media import images
from rbb_bot.infrastructure.media.images import ImageTooLarge, open_bounded
from rbb_bot.views.media import LEFT, CropView


def encode(image: Image.Image, format: str, **params) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=format, **params)
    return buffer.getvalue()


def bordered_png(size=(200, 120)) -> bytes:
    """White content inside a black border, so cropping visibly shrinks it."""
    image = Image.new("RGB", size, "black")
    ImageDraw.Draw(image).rectangle((20, 20, size[0] - 21, size[1] - 21), fill="white")
    return encode(image, "PNG")


def animated_gif(frames: int, size=(4, 4)) -> bytes:
    # Alternating colours stop Pillow merging identical consecutive frames.
    sequence = [Image.new("L", size, 255 * (i % 2)) for i in range(frames)]
    return encode(sequence[0], "GIF", save_all=True, append_images=sequence[1:])


def make_cog(confirm=False):
    bot = SimpleNamespace(
        send_error=AsyncMock(),
        get_confirmation=AsyncMock(return_value=confirm),
        logger=Mock(),
    )
    return MediaCog(bot)


def make_ctx():
    return SimpleNamespace(
        interaction=None,
        message=SimpleNamespace(attachments=[]),
        send=AsyncMock(),
    )


def serve(payloads: dict[str, bytes]):
    return patch.object(
        media_cog, "http_get", new=AsyncMock(side_effect=lambda url: payloads[url])
    )


def sent_texts(ctx) -> list[str]:
    return [call.args[0] for call in ctx.send.await_args_list if call.args]


def sent_files(ctx) -> list:
    return [
        call.kwargs["file"]
        for call in ctx.send.await_args_list
        if "file" in call.kwargs and "view" not in call.kwargs
    ]


def decode(file) -> Image.Image:
    file.fp.seek(0)
    return Image.open(BytesIO(file.fp.read()))


def test_oversized_png_is_rejected_from_the_header_without_decoding():
    # 6000×6000 is 36M pixels: under Pillow's own bomb limit, over ours.
    data = encode(Image.new("1", (6000, 6000)), "PNG")
    assert len(data) < 100_000
    with patch.object(
        ImageFile.ImageFile, "load", autospec=True, side_effect=AssertionError
    ) as load:
        with pytest.raises(ImageTooLarge, match="6000×6000"):
            open_bounded(data)
    load.assert_not_called()


def test_animation_over_the_frame_limit_is_rejected():
    with pytest.raises(ImageTooLarge, match="101 frames"):
        open_bounded(animated_gif(101))


def test_total_pixel_frames_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(images, "MAX_TOTAL_PIXEL_FRAMES", 4 * 4 * 3)
    open_bounded(animated_gif(3)).close()
    with pytest.raises(ImageTooLarge, match="in total"):
        open_bounded(animated_gif(4))


def test_pillow_decompression_bomb_becomes_a_clean_rejection(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)
    with pytest.raises(ImageTooLarge):
        open_bounded(encode(Image.new("L", (10, 10)), "PNG"))


def test_images_within_limits_are_fully_decoded():
    image = open_bounded(animated_gif(images.MAX_FRAMES))
    assert image.n_frames == images.MAX_FRAMES and image.size == (4, 4)
    assert image.getpixel((0, 0)) is not None
    image.close()


@pytest.mark.asyncio
async def test_only_the_first_five_sources_are_processed():
    urls = [f"https://example.test/{i}.png" for i in range(MAX_SOURCES + 2)]
    payloads = {url: bordered_png() for url in urls}
    ctx = make_ctx()
    with serve(payloads) as http_get:
        await MediaCog.rotate_image.callback(make_cog(), ctx, 90, urls=" ".join(urls))
    assert [call.args[0] for call in http_get.await_args_list] == urls[:MAX_SOURCES]
    assert [f.filename for f in sent_files(ctx)] == [
        f"{i}.png" for i in range(MAX_SOURCES)
    ]
    assert any("ignored the other 2" in text for text in sent_texts(ctx))


@pytest.mark.asyncio
async def test_each_source_is_sent_and_released_before_the_next_is_fetched():
    opened = []
    events = []

    def is_closed(image):
        try:
            image.getpixel((0, 0))
            return False
        except ValueError:
            return True

    def opening(data):
        opened.append(open_bounded(data))
        return opened[-1]

    async def fetch(url):
        events.append(("fetch", url[-5:], all(map(is_closed, opened))))
        return bordered_png()

    ctx = make_ctx()
    ctx.send.side_effect = lambda *a, **kw: events.append(("send", kw["file"].filename))
    with (
        patch.object(media_cog, "http_get", new=AsyncMock(side_effect=fetch)),
        patch.object(media_cog, "open_bounded", opening),
    ):
        await MediaCog.flip_image.callback(
            make_cog(), ctx, "v", urls="https://example.test/a.png https://e.test/b.png"
        )
    assert events == [
        ("fetch", "a.png", True),
        ("send", "a.png"),
        ("fetch", "b.png", True),
        ("send", "b.png"),
    ]
    assert all(map(is_closed, opened))


@pytest.mark.asyncio
async def test_over_limit_image_is_reported_to_the_user_and_others_still_sent(
    monkeypatch,
):
    monkeypatch.setattr(images, "MAX_FRAME_PIXELS", 50 * 50)
    payloads = {
        "https://example.test/big.png": bordered_png((200, 200)),
        "https://example.test/small.png": encode(Image.new("RGB", (40, 40)), "PNG"),
    }
    cog = make_cog()
    ctx = make_ctx()
    with serve(payloads):
        await MediaCog.crop_images.callback(cog, ctx, urls=" ".join(payloads))
    assert any(
        text.startswith("Image big.png is too large") for text in sent_texts(ctx)
    )
    assert [f.filename for f in sent_files(ctx)] == ["small.png"]
    cog.bot.send_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_crop_adjust_reports_an_over_limit_image(monkeypatch):
    monkeypatch.setattr(images, "MAX_FRAMES", 2)
    cog = make_cog()
    ctx = make_ctx()
    with serve({"https://example.test/anim.gif": animated_gif(3)}):
        await MediaCog.crop_adjust.callback(cog, ctx, "https://example.test/anim.gif")
    assert sent_texts(ctx) == [
        "Image anim.gif is too large to process: 3 frames is more than 2"
    ]
    cog.bot.send_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_crop_sends_the_cropped_image_and_offers_a_crop_view():
    cog = make_cog(confirm=True)
    ctx = make_ctx()
    with serve({"https://example.test/a.png": bordered_png()}):
        await MediaCog.crop_images.callback(cog, ctx, urls="https://example.test/a.png")
    [file] = sent_files(ctx)
    assert file.filename == "a.png"
    assert decode(file).width < 200 and decode(file).height < 120
    view = ctx.send.await_args.kwargs["view"]
    assert isinstance(view, CropView) and view.image.size == decode(file).size
    await view.stop_view()


@pytest.mark.asyncio
async def test_rotate_flip_and_webp_send_transformed_images():
    source = Image.new("RGB", (40, 20), "white")
    source.putpixel((0, 0), (255, 0, 0))
    png, webp = "https://example.test/pic.png", "https://example.test/pic.webp"
    payloads = {png: encode(source, "PNG"), webp: encode(source, "WEBP")}
    cog = make_cog()

    ctx = make_ctx()
    with serve(payloads):
        await MediaCog.rotate_image.callback(cog, ctx, 90, urls=png)
    assert decode(sent_files(ctx)[0]).size == (20, 40)

    ctx = make_ctx()
    with serve(payloads):
        await MediaCog.flip_image.callback(cog, ctx, "h", urls=png)
    flipped = decode(sent_files(ctx)[0]).convert("RGB")
    assert flipped.getpixel((39, 0)) == (255, 0, 0)

    ctx = make_ctx()
    with serve(payloads):
        await MediaCog.convert_webp.callback(cog, ctx, urls=webp)
    [file] = sent_files(ctx)
    assert file.filename == "pic.png" and decode(file).format == "PNG"
    cog.bot.send_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_pillow_work_runs_off_the_event_loop():
    loop_thread = threading.get_ident()
    threads = []

    def recording(function):
        def wrapper(*args, **kwargs):
            threads.append(threading.get_ident())
            return function(*args, **kwargs)

        return wrapper

    ctx = make_ctx()
    with (
        serve({"https://example.test/a.png": bordered_png()}),
        patch.object(media_cog, "open_bounded", recording(open_bounded)),
        patch.object(media_cog, "crop_image", recording(media_cog.crop_image)),
    ):
        await MediaCog.crop_images.callback(
            make_cog(), ctx, urls="https://example.test/a.png"
        )
    assert len(threads) == 2 and loop_thread not in threads


@pytest.mark.asyncio
async def test_crop_view_crops_off_the_event_loop():
    image = Image.new("RGB", (200, 200), "red")
    image.format = "PNG"
    view = CropView(Mock(), "image.png", image)
    view.message = SimpleNamespace(edit=AsyncMock())
    loop_thread = threading.get_ident()
    threads = []
    original = Image.Image.crop

    def crop(self, *args, **kwargs):
        threads.append(threading.get_ident())
        return original(self, *args, **kwargs)

    with patch.object(Image.Image, "crop", crop):
        await view.crop(LEFT)
    assert threads and loop_thread not in threads
    assert view.image.size == (195, 200)
    await view.stop_view()
