"""Frame loading and decoration, independent of native windows and sessions."""
from functools import lru_cache
from . import art
from .pet_pack import bundled_pack
from .image_codec import decode_png, encode_png
from .renderer.protocol import RgbaFrame


class FrameSource:
    @lru_cache(maxsize=80)
    def frame(self, pack: str, revision: str, reference: str) -> RgbaFrame:
        pose, index = reference.split('/')
        if pack == 'akita':
            image = art._ready_blink_icon() if index == 'blink' else art._akita_asset(pose, int(index))
        elif pack == 'robot':
            definition = bundled_pack(pack).frames[reference]
            image = art._robot_icon(definition.pose, definition.variant)
        else:
            raise ValueError('Unknown frame source')
        width, height, pixels = decode_png(image)
        return RgbaFrame((pack, revision, reference), width, height, bytes(pixels))


class FrameComposer:
    @lru_cache(maxsize=80)
    def compose(self, base: RgbaFrame, count: int) -> RgbaFrame:
        if count <= 1:
            return base
        pack, revision, reference = base.key
        count = min(count, 10)
        if pack == 'akita':
            image = art._add_count_badge(encode_png(base.width, base.height, base.pixels), count)
        else:
            pose, index = reference.split('/')
            image = art._robot_icon(pose, int(index), count)
        width, height, pixels = decode_png(image)
        return RgbaFrame((pack, revision, reference, count), width, height, bytes(pixels))
