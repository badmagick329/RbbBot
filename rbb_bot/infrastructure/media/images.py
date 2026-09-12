import numpy as np
from PIL import Image


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
