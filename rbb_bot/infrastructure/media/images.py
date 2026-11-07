from io import BytesIO

import numpy as np
from PIL import Image

# Image tools decode untrusted downloads inside the single bot process. A file
# under the download cap can still declare huge dimensions or frame counts, so
# these bounds are checked from the header before any pixel data is decoded.

# One RGBA frame of this size is ~100 MB once decoded; cropping copies it a few
# times more, which is as much as one command may hold.
MAX_FRAME_PIXELS = 25_000_000
# Animated GIF/WebP/APNG frames are decoded one by one when re-encoded; more than
# this is a stress test, not a reaction image.
MAX_FRAMES = 100
# Re-encoding with save_all walks every frame, so total work scales with
# width × height × frames even when each frame is within MAX_FRAME_PIXELS.
MAX_TOTAL_PIXEL_FRAMES = 100_000_000


class ImageTooLarge(Exception):
    """An image exceeds the decode bounds; `reason` is safe to show to the user."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def open_bounded(data: bytes) -> Image.Image:
    """
    Decode a downloaded image only after its header proves it fits the bounds.

    Pillow's own decompression-bomb limit is global and far looser than what one
    bot command should hold, so the limits are enforced here instead; Pillow's
    `DecompressionBombError` is still mapped to `ImageTooLarge` so it never
    surfaces as an unexpected failure. Blocking: run it off the event loop.
    """
    try:
        image = Image.open(BytesIO(data))
    except Image.DecompressionBombError as e:
        raise ImageTooLarge("its dimensions exceed the decoder's safety limit") from e
    try:
        width, height = image.size
        frames = getattr(image, "n_frames", 1)
        if width * height > MAX_FRAME_PIXELS:
            raise ImageTooLarge(
                f"{width}×{height} is more than {MAX_FRAME_PIXELS:,} pixels"
            )
        if frames > MAX_FRAMES:
            raise ImageTooLarge(f"{frames} frames is more than {MAX_FRAMES}")
        if width * height * frames > MAX_TOTAL_PIXEL_FRAMES:
            raise ImageTooLarge(
                f"{width}×{height} across {frames} frames is more than "
                f"{MAX_TOTAL_PIXEL_FRAMES:,} pixels in total"
            )
        image.load()
    except Image.DecompressionBombError as e:
        image.close()
        raise ImageTooLarge("its dimensions exceed the decoder's safety limit") from e
    except BaseException:
        image.close()
        raise
    return image


def normalize_image(image):
    """Cropping needs color channels; retain transparency from palette and grayscale inputs."""
    return image.convert(
        "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
    )


def crop_image(img: Image.Image, threshold: int = 10) -> Image.Image:
    """
    Take an image and crop the solid line borders around it

    Parameters
    ----------
    img : Image.Image
        The image to crop
    threshold : int
        The threshold for considering 2 pixels to be the same color
    """
    img_data = np.asarray(normalize_image(img))
    mid_height = img_data.shape[0] // 2
    height = img_data.shape[0]
    width = img_data.shape[1]

    top_y = 0
    bottom_y = height
    GRAD_STEP = 20

    def is_close(pixel1: list[int], pixel2: list[int], threshold: int):
        for i in range(3):
            if abs(pixel1[i] - pixel2[i]) > threshold:
                return False
        return True

    def calc_top_y(img_data: np.ndarray, mid_height: int, additional_crop: int = 5):
        """
        Additional crop is to account for the noise in images esp jpg
        """
        top_y = 0
        for y in range(mid_height, 0, -1):
            top_y = y + additional_crop
            r_std = np.std(img_data[y, :, 0])
            g_std = np.std(img_data[y, :, 1])
            b_std = np.std(img_data[y, :, 2])
            if r_std < threshold and g_std < threshold and b_std < threshold:
                break
        return top_y

    def calc_bottom_y(img_data: np.ndarray, mid_height: int, additional_crop: int = 5):
        bottom_y = height
        for y in range(mid_height, height):
            bottom_y = y - additional_crop
            r_std = np.std(img_data[y, :, 0])
            g_std = np.std(img_data[y, :, 1])
            b_std = np.std(img_data[y, :, 2])
            if r_std < threshold and g_std < threshold and b_std < threshold:
                break
        return bottom_y

    def calc_left_x(
        img_data: np.ndarray, width: int, step: int, additional_crop: int = 5
    ):
        left_x = width - 2
        for y in range(top_y, bottom_y, step):
            x = 0
            while x < width - 2 and x < left_x:
                # if not np.allclose(img_data[y, 0, :], img_data[y, x+1, :], atol=threshold):
                if not is_close(
                    img_data[y, 0].tolist(), img_data[y, x + 1].tolist(), threshold
                ):
                    left_x = x
                    break
                x += 1
        return 0 if left_x == width - 2 else left_x + additional_crop

    def calc_right_x(
        img_data: np.ndarray, width: int, step: int, additional_crop: int = 5
    ):
        right_x = 0
        for y in range(top_y, bottom_y, step):
            x = width - 1
            while x > 2 and x > right_x:
                # if not np.allclose(img_data[y, width-1, :], img_data[y, x-1, :], atol=threshold):
                if not is_close(
                    img_data[y, width - 1].tolist(),
                    img_data[y, x - 1].tolist(),
                    threshold,
                ):
                    right_x = x
                    break
                x -= 1
        return width - 1 if right_x == 0 else right_x - additional_crop

    if height < 12 or width < 12:
        return Image.fromarray(img_data)
    top_y = calc_top_y(img_data, mid_height)
    bottom_y = calc_bottom_y(img_data, mid_height)
    if top_y >= bottom_y:
        return Image.fromarray(img_data)
    left_x = calc_left_x(img_data, width, GRAD_STEP)
    right_x = calc_right_x(img_data, width, GRAD_STEP)
    if left_x >= right_x:
        return Image.fromarray(img_data)
    return Image.fromarray(img_data[top_y:bottom_y, left_x:right_x, :])
