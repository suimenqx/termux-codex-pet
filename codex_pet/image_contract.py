"""Lightweight pixel allocation and fixed v1 display contract."""

MAX_IMAGE_BYTES = 64 * 1024 * 1024
DISPLAY_DP = (64, 64)


def rgba_size(width: int, height: int) -> int:
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise ValueError('Image dimensions must be positive integers')
    size = width * height * 4
    if size > MAX_IMAGE_BYTES:
        raise ValueError('Image exceeds decode budget')
    return size
