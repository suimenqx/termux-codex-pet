"""Historical artwork export aliases; not shipped in the installed runtime.

Kept for archived research and original artwork regression fingerprints.
All pixel preparation delegates to the production frame pipeline/codec.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from codex_pet.image_codec import decode_png as _decode_rgba_png, encode_png as _png
from codex_pet.pets import DEFAULT_APPEARANCE, appearance_for

SIZE = 64


AKITA_SIZE = 256
AKITA_ASSET_DIR = Path(__file__).resolve(
).parents[1] / 'codex_pet/assets/akita'


def _robot_icon(state: str, frame: int = 0, count: int = 0) -> bytes:
    from codex_pet.drawing import robot_pixels, robot_badge
    pixels = robot_pixels(state, frame)
    if state == 'running' and count > 1:
        pixels = robot_badge(SIZE, SIZE, pixels, min(count, 10))
    return _png(SIZE, SIZE, pixels)


def _akita_asset(state: str, frame: int) -> bytes:
    return (AKITA_ASSET_DIR / 'frames' / state / f'{frame:02}.png').read_bytes()


def _add_count_badge(image: bytes, count: int) -> bytes:
    from codex_pet.drawing import akita_badge
    width, height, pixels = _decode_rgba_png(image)
    return _png(width, height, akita_badge(width, height, bytes(pixels), min(count, 10)))


def _ready_blink_icon() -> bytes:
    """Historical export alias for the static, validated derived asset."""
    return (AKITA_ASSET_DIR / "derived/ready-blink.png").read_bytes()


@lru_cache(maxsize=1)
def _legacy_pipeline():
    from codex_pet.frames import FrameSource, FrameComposer
    from codex_pet.frame_cache import FrameCache
    cache = FrameCache()
    return FrameSource(cache), FrameComposer(cache)


def _legacy_frame(state: str, frame: int, count: int, appearance: str):
    from tools.historical_animation import frame_reference
    from codex_pet.pet_pack import bundled_pack
    pack = bundled_pack(appearance_for(appearance).id)
    source, composer = _legacy_pipeline()
    return composer.compose(source.frame(pack.id, pack.revision,
                            frame_reference(pack.id, state, frame)),
                            count if state == 'running' else 0)


def icon(state: str, frame: int = 0, count: int = 0,
         appearance: str = DEFAULT_APPEARANCE) -> bytes:
    """Historical PNG export facade; production callers use FrameSource."""
    image = _legacy_frame(state, frame, count, appearance)
    return _png(image.width, image.height, image.pixels)


def rgba_icon(state: str, frame: int = 0, count: int = 0) -> bytes:
    """Historical Akita pixel export facade over the production pipeline."""
    return _legacy_frame(state, frame, count, 'akita').pixels
