"""64 px robot and Akita pixel art drawn with the Python standard library."""

from __future__ import annotations

import struct
import zlib
from typing import Any

from .pets import APPEARANCE_BY_ID, DEFAULT_APPEARANCE

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


def _robot_icon(state: str, frame: int = 0, count: int = 0) -> bytes:
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
        "running": (83, 169, 255, 255),
        "needs_input": (255, 191, 75, 255),
        "ready": (95, 220, 146, 255),
        "blocked": (255, 108, 117, 255),
    }
    accent = colors.get(state, colors["idle"])
    shell = (31, 40, 52, 250)
    face = (43, 55, 70, 255)
    white = (241, 249, 255, 255)

    # Empty pixels around the mascot stay transparent; draw only the robot silhouette.
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
    if state == "ready":
        for cx in (24, 40):
            rect(cx - 4, 32, cx - 2, 34, white)
            rect(cx - 2, 29, cx + 2, 32, white)
            rect(cx + 2, 32, cx + 4, 34, white)
    else:
        eye_radius = 5 if state == "needs_input" else 4
        disc(24, 32, eye_radius, white)
        disc(40, 32, eye_radius, white)
        rect(23, 31, 25, 34, shell)
        rect(39, 31, 41, 34, shell)

    if state in ("idle", "ready"):
        rect(27, 41, 37, 43, accent)
        dot(26, 40, accent)
        dot(37, 40, accent)
    elif state == "running":
        rect(29, 42, 35, 44, accent)
    elif state == "needs_input":
        disc(32, 42, 3, accent)
        disc(32, 42, 1, face)
    elif state == "blocked":
        rect(27, 42, 29, 44, accent)
        rect(29, 40, 35, 42, accent)
        rect(35, 42, 37, 44, accent)

    if state == "running":
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
    elif state == "needs_input":
        disc(53, 12, 10 if frame else 9, (41, 49, 59, 255))
        disc(53, 12, 8, accent)
        rect(51, 7, 55, 10, shell)
        rect(54, 9, 57, 13, shell)
        rect(52, 13, 55, 16, shell)
        rect(52, 18, 55, 20, shell)
    elif state == "ready":
        disc(53, 12, 9, accent)
        for x, y in ((49, 12), (50, 13), (51, 14), (52, 13), (53, 12), (54, 11), (55, 10), (56, 9)):
            rect(x, y, x + 2, y + 2, shell)
    elif state == "blocked":
        disc(53, 12, 9, accent)
        rect(52, 6, 55, 14, shell)
        rect(52, 17, 55, 20, shell)

    return _png(SIZE, SIZE, pixels)


def _akita_icon(state: str, frame: int = 0, count: int = 0) -> bytes:
    pixels = bytearray(SIZE * SIZE * 4)

    def dot(x: int, y: int, color: tuple[int, int, int, int]) -> None:
        if 0 <= x < SIZE and 0 <= y < SIZE:
            offset = (y * SIZE + x) * 4
            pixels[offset:offset + 4] = bytes(color)

    def rect(x0: int, y0: int, x1: int, y1: int,
             color: tuple[int, int, int, int]) -> None:
        for y in range(y0, y1):
            for x in range(x0, x1):
                dot(x, y, color)

    def disc(cx: int, cy: int, radius: int,
             color: tuple[int, int, int, int]) -> None:
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                    dot(x, y, color)

    def line(x0: int, y0: int, x1: int, y1: int,
             color: tuple[int, int, int, int], width: int = 1) -> None:
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        radius = width // 2
        for step in range(steps + 1):
            x = round(x0 + (x1 - x0) * step / steps)
            y = round(y0 + (y1 - y0) * step / steps)
            rect(x - radius, y - radius, x - radius + width, y - radius + width, color)

    colors = {
        "idle": (91, 206, 194, 255),
        "running": (83, 169, 255, 255),
        "needs_input": (255, 191, 75, 255),
        "ready": (95, 220, 146, 255),
        "blocked": (255, 108, 117, 255),
    }
    accent = colors.get(state, colors["idle"])
    outline = (76, 44, 35, 255)
    coat = (226, 106, 38, 255)
    coat_light = (247, 149, 54, 255)
    coat_shadow = (186, 68, 31, 255)
    cream = (246, 231, 199, 255)
    cream_shadow = (223, 202, 164, 255)
    dark = (49, 39, 34, 255)
    eye_glint = (255, 250, 231, 255)
    tongue = (224, 112, 122, 255)

    def badge() -> None:
        if state == "running" and count > 1:
            disc(55, 9, 8, outline)
            disc(55, 9, 6, accent)
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
            left = 55 - (4 * len(label) - 1) // 2
            for column, char in enumerate(label):
                for y, row in enumerate(digits[char]):
                    for x, pixel in enumerate(row):
                        if pixel == "1":
                            dot(left + column * 4 + x, 7 + y, outline)
        elif state == "needs_input":
            disc(55, 9, 8, outline)
            disc(55, 9, 6, accent)
            for y, row in enumerate(("01110", "10001", "00001", "00010",
                                     "00100", "00000", "00100")):
                for x, pixel in enumerate(row):
                    if pixel == "1":
                        dot(52 + x, 4 + y, dark)
        elif state == "ready":
            disc(55, 9, 7, outline)
            disc(55, 9, 5, accent)
            for x, y in ((51, 9), (52, 10), (53, 11), (54, 10),
                         (55, 9), (56, 8), (57, 7), (58, 6)):
                rect(x, y, x + 2, y + 2, outline)
        elif state == "blocked":
            disc(55, 9, 7, outline)
            disc(55, 9, 5, accent)
            rect(54, 3, 57, 10, dark)
            rect(54, 12, 57, 15, dark)

    if state == "running":
        _akita_running(frame, accent, outline, coat, coat_light, coat_shadow,
                       cream, cream_shadow, dark, tongue, disc, rect, line, dot)
    else:
        _akita_sitting(state, frame, accent, outline, coat, coat_light,
                       coat_shadow, cream, cream_shadow, dark, eye_glint, tongue,
                       disc, rect, line, dot)
    badge()
    return _png(SIZE, SIZE, pixels)


def _akita_sitting(state: str, frame: int,
                   accent: tuple[int, int, int, int],
                   outline: tuple[int, int, int, int],
                   coat: tuple[int, int, int, int],
                   coat_light: tuple[int, int, int, int],
                   coat_shadow: tuple[int, int, int, int],
                   cream: tuple[int, int, int, int],
                   cream_shadow: tuple[int, int, int, int],
                   dark: tuple[int, int, int, int],
                   eye_glint: tuple[int, int, int, int],
                   tongue: tuple[int, int, int, int], disc: Any,
                   rect: Any, line: Any, dot: Any) -> None:
    bob = (0, 1, 0)[frame % 3] if state == "idle" else 0
    if state == "ready":
        bob = (0, -1, -3, -2, 0)[min(frame, 4)]
    if state == "blocked" and frame >= 1:
        bob = 1

    def d(cx: int, cy: int, radius: int, color: tuple[int, int, int, int]) -> None:
        disc(cx, cy + bob, radius, color)

    def r(x0: int, y0: int, x1: int, y1: int,
          color: tuple[int, int, int, int]) -> None:
        rect(x0, y0 + bob, x1, y1 + bob, color)

    # The small body stays behind a large, friendly head.
    tail_x = 15 + (1 if state == "idle" and frame == 1 else 0)
    d(tail_x, 40, 7, outline)
    d(tail_x, 40, 5, coat_light)
    d(tail_x, 40, 2, (0, 0, 0, 0))
    r(tail_x - 6, 34, tail_x - 3, 37, cream)
    r(16, 38, 24, 46, coat_shadow)

    # Compact body and paws peek out below the large head.
    r(19, 41, 45, 56, outline)
    d(25, 48, 7, outline)
    d(39, 48, 7, outline)
    r(21, 41, 43, 54, coat)
    d(25, 47, 5, coat_light)
    d(39, 47, 5, coat)
    r(24, 49, 40, 55, cream_shadow)
    r(22, 52, 31, 60, outline)
    r(33, 52, 42, 60, outline)
    r(24, 53, 30, 58, coat_light)
    r(34, 53, 40, 58, coat_light)
    r(25, 56, 29, 58, cream_shadow)
    r(35, 56, 39, 58, cream_shadow)

    # Small, integrated ears frame the orange crown instead of making a fox point.
    ear_top = 7 if state == "needs_input" else 9
    if state == "blocked":
        ear_top = 11
    ear_widths = (2, 3, 5, 6, 7, 8, 9)
    for center in (22, 42):
        for row, width in enumerate(ear_widths):
            y = ear_top + row
            left = center - width // 2
            rect(left, y + bob, left + width, y + bob + 1, outline)
            if row >= 2:
                inner_width = max(1, width - 5)
                inner_left = center - inner_width // 2
                rect(inner_left, y + 1 + bob, inner_left + inner_width,
                     y + 2 + bob, coat_shadow)

    # Round head, orange cap, broad pale face, and a narrow forehead blaze.
    d(32, 29, 20, outline)
    r(14, 22, 50, 40, outline)
    d(32, 29, 18, coat)
    r(16, 21, 48, 38, coat)
    r(30, 14, 34, 28, cream)
    r(31, 13, 33, 25, cream_shadow)
    d(32, 36, 14, cream)
    r(19, 29, 45, 44, cream)
    d(20, 37, 7, cream)
    d(44, 37, 7, cream)
    r(24, 41, 40, 47, cream)
    r(25, 43, 39, 45, cream_shadow)

    # Tiny eyes sit in the pale face; the black nose and open smile read at icon size.
    r(22, 27, 26, 31, dark)
    r(38, 27, 42, 31, dark)
    dot(23, 27 + bob, eye_glint)
    dot(39, 27 + bob, eye_glint)
    r(30, 34, 34, 36, dark)
    dot(29, 34, dark)
    dot(34, 34, dark)

    if state == "needs_input":
        # The eager, open smile pairs with the raised paw.
        r(31, 36, 33, 38, dark)
        r(29, 38, 35, 43, dark)
        r(30, 41, 34, 44, tongue)
    elif state == "ready":
        line(22, 28 + bob, 26, 28 + bob, dark, 2)
        line(38, 28 + bob, 42, 28 + bob, dark, 2)
        r(31, 36, 33, 38, dark)
        r(29, 38, 35, 43, dark)
        r(29, 40, 35, 44, tongue)
    elif state == "blocked":
        line(22, 26 + bob, 26, 29 + bob, dark, 2)
        line(38, 29 + bob, 42, 26 + bob, dark, 2)
        line(30, 40 + bob, 32, 42 + bob, dark, 2)
        line(32, 42 + bob, 35, 39 + bob, dark, 2)
    else:
        r(31, 36, 33, 38, dark)
        r(29, 38, 35, 42, dark)
        r(30, 40, 34, 43, tongue)

    # Keep the status collar on the small visible chest below the chin.
    r(24, 49, 40, 52, accent)
    d(32, 53, 3, outline)
    d(32, 53, 1, accent)

    if state == "needs_input":
        # Raise a small paw beside the cheek so the face stays readable.
        paw_y = 44 if frame in (0, 3) else 42
        r(43, paw_y, 49, paw_y + 7, outline)
        r(44, paw_y + 1, 48, paw_y + 5, coat_light)
        r(45, paw_y + 4, 48, paw_y + 6, cream)
    elif state == "blocked":
        # A paw to the cheek gives the stuck pose a puzzled, mildly comic feel.
        paw_y = 34 if frame % 2 else 36
        r(42, paw_y, 48, paw_y + 6, outline)
        r(43, paw_y + 1, 47, paw_y + 5, coat_light)
        r(44, paw_y + 3, 47, paw_y + 5, cream)

    if state == "ready" and frame in (1, 2):
        for x, y in ((8, 20), (12, 15), (48, 24)):
            dot(x, y + bob, accent)


def _akita_running(frame: int,
                   accent: tuple[int, int, int, int],
                   outline: tuple[int, int, int, int],
                   coat: tuple[int, int, int, int],
                   coat_light: tuple[int, int, int, int],
                   coat_shadow: tuple[int, int, int, int],
                   cream: tuple[int, int, int, int],
                   cream_shadow: tuple[int, int, int, int],
                   dark: tuple[int, int, int, int],
                   tongue: tuple[int, int, int, int], disc: Any,
                   rect: Any, line: Any, dot: Any) -> None:
    pose = frame % 4
    body_y = (0, -1, 0, 1)[pose]

    def r(x0: int, y0: int, x1: int, y1: int,
          color: tuple[int, int, int, int]) -> None:
        rect(x0, y0 + body_y, x1, y1 + body_y, color)

    # Speed marks and the high Akita tail curl stay inside the canvas.
    for x, y, length in ((3, 20, 7), (5, 31, 5), (2, 43, 8)):
        r(x, y + pose % 2, x + length, y + pose % 2 + 2, accent)
    tail_y = 25 + int(pose in (0, 3)) + body_y
    disc(16, tail_y, 7, outline)
    disc(16, tail_y, 5, coat_light)
    disc(16, tail_y, 2, (0, 0, 0, 0))
    r(9, tail_y - 5 - body_y, 12, tail_y - 2 - body_y, cream)

    # Four short, thick legs alternate through a compact springing stride.
    feet = (
        ((48, 49), (41, 51), (14, 49), (23, 51)),
        ((39, 51), (49, 48), (18, 51), (12, 47)),
        ((49, 48), (41, 51), (13, 48), (24, 51)),
        ((39, 50), (49, 51), (20, 51), (12, 46)),
    )[pose]
    anchors = ((38, 34), (35, 35), (22, 35), (25, 35))
    bends = ((44, 39), (39, 42), (17, 41), (22, 42))
    for index, ((ax, ay), (bx, by), (fx, fy)) in enumerate(zip(anchors, bends, feet)):
        far = index in (1, 3)
        leg = coat_shadow if far else coat
        paw = cream_shadow if far else coat_light
        line(ax, ay + body_y, bx, by + body_y, outline, 7)
        line(ax, ay + body_y, bx, by + body_y, leg, 5)
        line(bx, by + body_y, fx, fy + body_y, outline, 6)
        line(bx, by + body_y, fx, fy + body_y, leg, 4)
        r(fx - 3, fy - 1, fx + 3, fy + 2, paw)

    # A compact, deep-chested body gives the running pose a sturdy silhouette.
    r(17, 25, 43, 41, outline)
    disc(24, 32 + body_y, 10, outline)
    disc(37, 32 + body_y, 10, outline)
    r(20, 25, 41, 39, coat)
    disc(24, 31 + body_y, 8, coat)
    disc(37, 31 + body_y, 8, coat_light)
    r(30, 33, 41, 40, cream)
    r(36, 31, 44, 38, accent)
    r(37, 32, 43, 36, outline)

    # Broad side-view skull, small set ears, blunt muzzle, and visible jaw.
    disc(45, 27 + body_y, 10, outline)
    r(40, 20 + body_y, 51, 34 + body_y, outline)
    disc(45, 27 + body_y, 8, coat)
    r(41, 21 + body_y, 50, 30 + body_y, coat)
    for center, top, height in ((43, 14, 7), (50, 16, 6)):
        widths = (2, 3, 5, 7, 8, 8, 8)[:height]
        for row, width in enumerate(widths):
            x0 = center - width // 2
            y = top + row + body_y
            rect(x0, y, x0 + width, y + 1, outline)
            if row >= 2:
                inner = max(1, width - 5)
                rect(center - inner // 2, y + 1,
                     center - inner // 2 + inner, y + 2, coat_shadow)

    # Repeat the Akita's orange crown and pale face split in profile.
    r(43, 18 + body_y, 45, 28 + body_y, cream)
    disc(43, 30 + body_y, 7, cream)
    r(42, 28 + body_y, 50, 34 + body_y, cream)
    r(47, 28 + body_y, 59, 36 + body_y, outline)
    r(48, 29 + body_y, 57, 34 + body_y, cream)
    r(56, 28 + body_y, 60, 31 + body_y, dark)
    dot(45, 24 + body_y, dark)
    dot(44, 23 + body_y, (255, 249, 232, 255))
    r(52, 35 + body_y, 56, 37 + body_y, dark)
    if pose in (0, 2):
        r(53, 37 + body_y, 56, 39 + body_y, tongue)

    # A single stride spark keeps the loop energetic without obscuring the dog.
    if pose in (0, 2):
        dot(8, 51, accent)
        dot(12, 54, accent)


def icon(state: str, frame: int = 0, count: int = 0,
         appearance: str = DEFAULT_APPEARANCE) -> bytes:
    """Draw one PNG frame for a registered pet appearance."""
    if appearance not in APPEARANCE_BY_ID:
        appearance = DEFAULT_APPEARANCE
    if appearance == "robot":
        return _robot_icon(state, frame, count)
    if appearance == "akita":
        return _akita_icon(state, frame, count)
    # Bad or future config values must never prevent the overlay from rendering.
    return _akita_icon(state, frame, count)


def animation_interval(appearance: str, state: str, frame: int) -> float | None:
    """Return the next frame delay; None means the current pose can rest."""
    if appearance == "akita":
        if state == "idle":
            return 1.0
        if state == "running":
            return 0.14
        if state == "needs_input":
            return 0.28
        if state == "ready" and frame < 4:
            return 0.14
        if state == "blocked" and frame < 3:
            return 0.18
        return None
    if state == "running":
        return 2.0
    if state == "needs_input":
        return 1.4
    return None


def advance_animation(appearance: str, state: str, frame: int) -> int:
    if appearance == "akita":
        if state == "idle":
            return (frame + 1) % 3
        if state == "running":
            return (frame + 1) % 4
        if state == "needs_input":
            return (frame + 1) % 4
        if state == "ready":
            return min(frame + 1, 4)
        if state == "blocked":
            return min(frame + 1, 3)
        return 0
    if state in ("running", "needs_input"):
        return 1 - frame
    return frame
