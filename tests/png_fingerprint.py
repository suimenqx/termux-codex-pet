"""Frozen pre-Pillow PNG serialization, only to verify archived fingerprints.

Production has one Pillow codec. This test oracle reconstructs the historical
unfiltered PNG stream from decoded pixels when archived exports retain only a
PNG hash, allowing a new compression strategy without weakening pixel checks.
"""
import hashlib
import struct
import zlib
from codex_pet.image_codec import decode_png


def historical_png_sha256(encoded: bytes) -> str:
    width, height, pixels = decode_png(encoded)
    raw = b''.join(
        b'\0' + pixels[y * width * 4:(y + 1) * width * 4] for y in range(height))

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    historical = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', width, height, 8, 6, 0, 0, 0))
                  + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))
    return hashlib.sha256(historical).hexdigest()
