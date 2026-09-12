import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from rbb_bot.views.media import CropView, LEFT


def make_view():
    image = Image.new("RGB", (200, 200), "red")
    image.format = "PNG"
    view = CropView(Mock(), "image.png", image)
    view.message = SimpleNamespace(edit=AsyncMock())
    return view


@pytest.mark.asyncio
async def test_failed_close_still_releases_image_and_disables_callbacks():
    view = make_view()
    view.message.edit.side_effect = RuntimeError("message deleted")
    with pytest.raises(RuntimeError):
        await view.stop_view()
    assert view.is_finished() and view.image is None and not view.children
    await view.crop(LEFT)
    assert view.message.edit.await_count == 1


@pytest.mark.asyncio
async def test_close_waits_for_active_crop_and_cannot_be_reopened():
    view = make_view()
    upload_started = asyncio.Event()
    finish_upload = asyncio.Event()

    async def edit(**kwargs):
        if "attachments" in kwargs:
            upload_started.set()
            await finish_upload.wait()

    view.message.edit.side_effect = edit
    cropping = asyncio.create_task(view.crop(LEFT))
    await asyncio.wait_for(upload_started.wait(), timeout=2)
    closing = asyncio.create_task(view.stop_view())
    finish_upload.set()
    await asyncio.wait_for(asyncio.gather(cropping, closing), timeout=2)
    assert view.crop_count == 1
    assert view.is_finished() and view.image is None
    assert view.message.edit.call_args.kwargs["content"] is None
    await view.crop(LEFT)
    assert view.crop_count == 1


@pytest.mark.asyncio
async def test_failed_upload_preserves_image_and_can_be_retried():
    view = make_view()
    original = view.image
    view.message.edit.side_effect = RuntimeError("upload failed")
    with pytest.raises(RuntimeError):
        await view.crop(LEFT)
    assert view.image is original and view.crop_count == 0
    view.message.edit.side_effect = None
    await view.crop(LEFT)
    assert view.image.size == (195, 200)
    assert view.image.getpixel((0, 0)) == (255, 0, 0)
    assert view.crop_count == 1
    await view.stop_view()


@pytest.mark.asyncio
async def test_failed_initial_send_releases_crop_view():
    view = make_view()
    view.message = None
    view.ctx.send = AsyncMock(side_effect=RuntimeError("send failed"))
    with pytest.raises(RuntimeError):
        await view.send(Mock())
    assert view.is_finished() and view.image is None
