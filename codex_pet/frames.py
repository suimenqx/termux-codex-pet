"""Immutable frame loading and decoration through one managed byte budget."""
from .drawing import robot_pixels, robot_badge, akita_badge
from .frame_cache import FrameCache
from .pet_pack import bundled_pack
from .image_codec import decode_png, MAX_DECODE_BYTES
from .renderer.protocol import RgbaFrame


class FrameSource:
    def __init__(self, cache: FrameCache | None = None):
        self.cache = cache if cache is not None else FrameCache()

    def frame(self, pack: str, revision: str, reference: str) -> RgbaFrame:
        compiled = bundled_pack(pack)
        if compiled.revision != revision:
            raise ValueError(
                'Frame request belongs to a different pack revision')
        definition = compiled.frames[reference]
        key = (pack, revision, reference)
        pixels = self.cache.get(('base', key))
        width, height = compiled.canvas
        if pixels is None:
            if definition.file is not None:
                if definition.file.stat().st_size > MAX_DECODE_BYTES:
                    raise ValueError('Encoded frame exceeds byte budget')
                w, h, decoded = decode_png(definition.file.read_bytes())
                if (w, h) != (width, height):
                    raise ValueError('Frame dimensions differ from pack')
                pixels = bytes(decoded)
            else:
                pixels = robot_pixels(definition.pose, definition.variant)
            self.cache.put(('base', key), pixels, base=True)
        return RgbaFrame(key, width, height, pixels)


class FrameComposer:
    def __init__(self, cache: FrameCache | None = None):
        self.cache = cache if cache is not None else FrameCache()

    def compose(self, base: RgbaFrame, count: int) -> RgbaFrame:
        if count <= 1:
            return base
        pack, revision, reference = base.key
        count = min(count, 10)
        key = (pack, revision, reference, count)
        pixels = self.cache.get(('derived', key))
        if pixels is None:
            style = bundled_pack(pack).decoration
            draw = robot_badge if style == 'robot_count_v1' else akita_badge
            pixels = draw(base.width, base.height, base.pixels, count)
            self.cache.put(('derived', key), pixels)
        return RgbaFrame(key, base.width, base.height, pixels)
