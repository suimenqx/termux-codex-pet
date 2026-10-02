"""Lazy Pillow conversion to tightly packed, straight-alpha sRGB RGBA8.

Untagged PNGs are interpreted as sRGB under the pet asset contract. Other
profiles are rejected, not silently converted or stripped.
"""
from __future__ import annotations
from io import BytesIO
import struct
from .image_contract import MAX_IMAGE_BYTES as MAX_DECODE_BYTES, rgba_size

_CAPABILITY_PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
    '0000000d49444154789c63300aa8680000032d017bc223cb020000000049454e44ae426082')
_SRGB_CHROMATICITY = (.3127, .3290, .64, .33, .30, .60, .15, .06)


def _check_container(data: bytes) -> None:
    if len(data) > MAX_DECODE_BYTES or data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Expected PNG within encoded byte budget')
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        tag = data[offset + 4:offset + 8]
        if offset + 12 + length > len(data):
            raise ValueError('Truncated PNG chunk')
        if tag in (b'iCCP', b'cICP', b'mDCV', b'cLLI'):
            raise ValueError('Unsupported PNG color profile')
        offset += 12 + length
        if tag == b'IEND':
            break


def decode_png(data: bytes) -> tuple[int, int, bytearray]:
    from PIL import Image
    _check_container(data)
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != 'PNG':
                raise ValueError('Expected PNG')
            width, height = image.size
            rgba_size(width, height)
            info = image.info
            if 'srgb' in info and info['srgb'] not in (0, 1, 2, 3):
                raise ValueError('Invalid sRGB rendering intent')
            if 'gamma' in info and abs(info['gamma'] - .45455) > .00001:
                raise ValueError('Unsupported PNG gamma')
            if 'chromaticity' in info:
                values = info['chromaticity']
                if len(values) != 8 or any(abs(a - b) > .00001 for a, b in zip(values, _SRGB_CHROMATICITY)):
                    raise ValueError('Unsupported PNG chromaticity')
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            with image.convert('RGBA') as rgba:
                pixels = rgba.tobytes()
        if len(pixels) != width * height * 4:
            raise ValueError('Unexpected RGBA stride')
        return width, height, bytearray(pixels)
    except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError(f'Cannot decode PNG: {exc}') from exc


def encode_png(width: int, height: int, pixels: bytes | bytearray) -> bytes:
    from PIL import Image
    rgba_size(width, height)
    if len(pixels) != width * height * 4:
        raise ValueError('Expected tightly packed RGBA8')
    output = BytesIO()
    with Image.frombytes('RGBA', (width, height), bytes(pixels)) as image:
        image.save(output, format='PNG', compress_level=6)
    return output.getvalue()


def premultiply(width: int, height: int, pixels: bytes) -> bytes:
    from PIL import Image
    rgba_size(width, height)
    if len(pixels) != width * height * 4:
        raise ValueError('Expected tightly packed RGBA8')
    with Image.frombytes('RGBA', (width, height), pixels) as image:
        with image.convert('RGBa') as premultiplied:
            return premultiplied.tobytes()


def check_capability() -> None:
    """Exercise the actual PNG decoder, not merely the Pillow import."""
    try:
        if decode_png(_CAPABILITY_PNG) != (1, 1, bytearray((50, 80, 120, 128))):
            raise ValueError('PNG decoder changed the capability fixture')
    except (ImportError, OSError, ValueError, AttributeError) as exc:
        raise ValueError(f'Pillow PNG capability unavailable: {exc}') from exc
