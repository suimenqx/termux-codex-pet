"""Whitelisted builtin pixels and count decorations; no codecs or native APIs."""
SIZE = 64


def robot_pixels(state: str, frame: int = 0) -> bytes:
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

    return bytes(pixels)


def akita_badge(width: int, height: int, source: bytes, count: int) -> bytes:
    pixels = bytearray(source)
    scale_x = width / SIZE
    scale_y = height / SIZE
    center_x = round(57 * scale_x)
    center_y = round(6 * scale_y)
    outline = (76, 44, 35, 255)
    accent = (83, 169, 255, 255)

    def disc(cx: int, cy: int, radius: int,
             color: tuple[int, int, int, int]) -> None:
        for dy in range(-radius, radius + 1):
            span = int((radius * radius - dy * dy) ** 0.5)
            y = cy + dy
            if not 0 <= y < height:
                continue
            x0 = max(0, cx - span)
            x1 = min(width, cx + span + 1)
            if x0 < x1:
                start = (y * width + x0) * 4
                pixels[start:(y * width + x1) * 4] = bytes(color) * (x1 - x0)

    def square(x0: int, y0: int, size: int,
               color: tuple[int, int, int, int]) -> None:
        for y in range(max(0, y0), min(height, y0 + size)):
            start_x = max(0, x0)
            end_x = min(width, x0 + size)
            start = (y * width + start_x) * 4
            pixels[start:(y * width + end_x) *
                   4] = bytes(color) * (end_x - start_x)

    radius = round(5 * min(scale_x, scale_y))
    disc(center_x, center_y, radius, outline)
    disc(center_x, center_y, round(3.8 * min(scale_x, scale_y)), accent)

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
    cell = max(1, round(min(scale_x, scale_y)))
    label_width = (4 * len(label) - 1) * cell
    left = center_x - label_width // 2
    top = center_y - (5 * cell) // 2
    for column, char in enumerate(label):
        for row, glyph_row in enumerate(digits[char]):
            for x, pixel in enumerate(glyph_row):
                if pixel == "1":
                    square(left + column * 4 * cell + x * cell,
                           top + row * cell, cell, outline)

    return bytes(pixels)


def robot_badge(width: int, height: int, source: bytes, count: int) -> bytes:
    if (width, height) != (64, 64):
        raise ValueError('robot_count_v1 requires a 64-square canvas')
    pixels = bytearray(source)
    shell, accent = (31, 40, 52, 250), (83, 169, 255, 255)

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
    return bytes(pixels)
