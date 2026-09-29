"""Original 64 px robot drawn with the Python standard library."""

from __future__ import annotations

import struct
import zlib

SIZE = 64


def _png(width: int, height: int, pixels: bytearray) -> bytes:
    raw = b"".join(b"\0" + pixels[y * width * 4:(y + 1) * width * 4]
                   for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def speech_tail(toward: str) -> bytes:
    """Return a small transparent triangle pointing toward the robot."""
    if toward not in ("left", "right"):
        raise ValueError("speech tail direction must be 'left' or 'right'")
    width, height = 16, 28
    color = (32, 43, 54, 238)
    pixels = bytearray(width * height * 4)
    center = (height - 1) / 2
    for y in range(height):
        span = max(1, round(width * (1 - abs(y - center) / (height / 2))))
        for offset in range(span):
            x = offset if toward == "right" else width - 1 - offset
            start = (y * width + x) * 4
            pixels[start:start + 4] = bytes(color)
    return _png(width, height, pixels)


def icon(state: str, frame: int = 0, count: int = 0) -> bytes:
    pixels = bytearray(SIZE * SIZE * 4)

    def dot(x: int, y: int, color: tuple[int, int, int, int]) -> None:
        if 0 <= x < SIZE and 0 <= y < SIZE:
            pixels[(y * SIZE + x) * 4:(y * SIZE + x) * 4 + 4] = bytes(color)

    def rect(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int, int]) -> None:
        for y in range(y0, y1):
            for x in range(x0, x1):
                dot(x, y, color)

    def disc(cx: int, cy: int, radius: int, color: tuple[int, int, int, int]) -> None:
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                    dot(x, y, color)

    colors = {
        "idle": (91, 206, 194, 255),
        "working": (83, 169, 255, 255),
        "approval": (255, 191, 75, 255),
        "done": (95, 220, 146, 255),
        "interrupted": (181, 164, 255, 255),
        "error": (255, 108, 117, 255),
    }
    accent = colors.get(state, colors["idle"])
    shell = (31, 40, 52, 250)
    face = (43, 55, 70, 255)
    white = (241, 249, 255, 255)

    # Antenna, ears, softly rounded head and small body.
    disc(32, 34, 28, (18, 28, 39, 180))
    rect(30, 5, 34, 14, accent)
    disc(32, 5, 4, accent)
    rect(6, 29, 13, 40, accent)
    rect(51, 29, 58, 40, accent)
    rect(20, 49, 44, 56, shell)
    rect(24, 55, 29, 60, accent)
    rect(35, 55, 40, 60, accent)
    rect(13, 18, 51, 51, shell)
    rect(17, 14, 47, 55, shell)
    rect(17, 18, 47, 49, face)
    rect(13, 23, 51, 46, face)
    rect(13, 18, 51, 21, accent)
    rect(13, 46, 51, 49, accent)
    rect(10, 23, 13, 46, accent)
    rect(51, 23, 54, 46, accent)
    # Small blush marks and a status light give the robot a little warmth.
    blush = (226, 126, 147, 255)
    disc(18, 39, 2, blush)
    disc(46, 39, 2, blush)
    rect(29, 51, 35, 55, face)
    disc(32, 53, 2, accent)

    # Let the face react to the same state as the status badge.
    if state == "done":
        for cx in (24, 40):
            rect(cx - 4, 32, cx - 2, 34, white)
            rect(cx - 2, 29, cx + 2, 32, white)
            rect(cx + 2, 32, cx + 4, 34, white)
    elif state == "interrupted":
        rect(20, 31, 28, 33, white)
        rect(36, 31, 44, 33, white)
    else:
        eye_radius = 5 if state == "approval" else 4
        disc(24, 32, eye_radius, white)
        disc(40, 32, eye_radius, white)
        rect(23, 31, 25, 34, shell)
        rect(39, 31, 41, 34, shell)

    if state in ("idle", "done"):
        rect(27, 41, 37, 43, accent)
        dot(26, 40, accent)
        dot(37, 40, accent)
    elif state == "working":
        rect(29, 42, 35, 44, accent)
    elif state == "approval":
        disc(32, 42, 3, accent)
        disc(32, 42, 1, face)
    elif state == "interrupted":
        rect(29, 41, 35, 43, accent)
    elif state == "error":
        rect(27, 42, 29, 44, accent)
        rect(29, 40, 35, 42, accent)
        rect(35, 42, 37, 44, accent)

    if state == "working":
        for x, y in ([(3, 13), (58, 12), (60, 52)] if frame else [(2, 50), (57, 10), (60, 28)]):
            disc(x, y, 2, accent)
        if count > 1:
            digits = {
                "2": ("111", "001", "111", "100", "111"),
                "3": ("111", "001", "111", "001", "111"),
                "4": ("101", "101", "111", "001", "001"),
                "5": ("111", "100", "111", "001", "111"),
                "6": ("111", "100", "111", "101", "111"),
                "7": ("111", "001", "010", "010", "010"),
                "8": ("111", "101", "111", "101", "111"),
                "9": ("111", "101", "111", "001", "111"),
                "+": ("000", "010", "111", "010", "000"),
            }
            label = str(count) if count < 10 else "9+"
            disc(55, 10, 10, shell)
            disc(55, 10, 8, accent)
            left = 55 - (4 * len(label) - 1) // 2
            for column, char in enumerate(label):
                for y, row in enumerate(digits[char]):
                    for x, pixel in enumerate(row):
                        if pixel == "1":
                            dot(left + column * 4 + x, 8 + y, shell)
    elif state == "approval":
        disc(53, 12, 10 if frame else 9, (41, 49, 59, 255))
        disc(53, 12, 8, accent)
        rect(51, 7, 55, 10, shell)
        rect(54, 9, 57, 13, shell)
        rect(52, 13, 55, 16, shell)
        rect(52, 18, 55, 20, shell)
    elif state == "done":
        disc(53, 12, 9, accent)
        for x, y in ((49, 12), (50, 13), (51, 14), (52, 13), (53, 12), (54, 11), (55, 10), (56, 9)):
            rect(x, y, x + 2, y + 2, shell)
    elif state == "interrupted":
        disc(53, 12, 9, accent)
        rect(49, 7, 52, 17, shell)
        rect(54, 7, 57, 17, shell)
    elif state == "error":
        disc(53, 12, 9, accent)
        rect(52, 6, 55, 14, shell)
        rect(52, 17, 55, 20, shell)

    return _png(SIZE, SIZE, pixels)
