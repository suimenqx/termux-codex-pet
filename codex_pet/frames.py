"""Frame loading and decoration, independent of native windows and sessions."""
from functools import lru_cache
from . import art
from .pet_pack import bundled_pack
from .image_codec import decode_png, encode_png
from .renderer.protocol import RgbaFrame


class FrameSource:
    @lru_cache(maxsize=80)
    def frame(self, pack: str, revision: str, reference: str) -> RgbaFrame:
        compiled = bundled_pack(pack)
        if compiled.revision != revision:
            raise ValueError('Frame request belongs to a different pack revision')
        definition = compiled.frames[reference]
        if definition.file is not None:
            image = definition.file.read_bytes()
        else:
            image = art._robot_icon(definition.pose, definition.variant)
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
