"""Original 64 px robot drawn with the Python standard library."""

from __future__ import annotations

import struct
import zlib

SIZE = 64


def icon(state: str, frame: int = 0) -> bytes:
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
    # Expressive eyes and a tiny mouth.
    disc(24, 32, 4, white)
    disc(40, 32, 4, white)
    rect(23, 31, 25, 34, shell)
    rect(39, 31, 41, 34, shell)
    rect(27, 41, 37, 43, accent)
    dot(26, 40, accent)
    dot(37, 40, accent)

    if state == "working":
        for x, y in ([(3, 13), (58, 12), (60, 52)] if frame else [(2, 50), (57, 10), (60, 28)]):
            disc(x, y, 2, accent)
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

    raw = b"".join(b"\0" + pixels[y * SIZE * 4:(y + 1) * SIZE * 4] for y in range(SIZE))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", SIZE, SIZE, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
