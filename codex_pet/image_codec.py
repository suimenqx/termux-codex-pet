"""PNG pixel conversion, isolated from asset selection and native windows.

The existing codec is retained behind this boundary until the Pillow ticket.
"""
from __future__ import annotations
import ctypes
import struct
import zlib

def encode_png(width: int, height: int, pixels: bytes | bytearray) -> bytes:
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


class _PNGImage(ctypes.Structure):
    _fields_ = [
        ("opaque", ctypes.c_void_p), ("version", ctypes.c_uint32),
        ("width", ctypes.c_uint32), ("height", ctypes.c_uint32),
        ("format", ctypes.c_uint32), ("flags", ctypes.c_uint32),
        ("colormap_entries", ctypes.c_uint32), ("warning_or_error", ctypes.c_uint32),
        ("message", ctypes.c_char * 64),
    ]


_LIBPNG: ctypes.CDLL | None
try:
    _LIBPNG = ctypes.CDLL("libpng16.so")
    _LIBPNG.png_image_begin_read_from_memory.argtypes = (
        ctypes.POINTER(_PNGImage), ctypes.c_void_p, ctypes.c_size_t)
    _LIBPNG.png_image_begin_read_from_memory.restype = ctypes.c_int
    _LIBPNG.png_image_finish_read.argtypes = (
        ctypes.POINTER(_PNGImage), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_int32, ctypes.c_void_p)
    _LIBPNG.png_image_finish_read.restype = ctypes.c_int
    _LIBPNG.png_image_free.argtypes = (ctypes.POINTER(_PNGImage),)
except (AttributeError, OSError):
    _LIBPNG = None


def decode_png(image: bytes) -> tuple[int, int, bytearray]:
    """Decode the illustration with libpng before drawing its live count badge."""
    if _LIBPNG is None:
        raise ValueError("libpng is unavailable")
    source = ctypes.create_string_buffer(image)
    decoded = _PNGImage()
    decoded.version = 1
    pointer = ctypes.byref(decoded)
    try:
        if not _LIBPNG.png_image_begin_read_from_memory(pointer, source, len(image)):
            raise ValueError(decoded.message.decode("utf-8", "replace"))
        width, height = int(decoded.width), int(decoded.height)
        if width <= 0 or height <= 0 or width * height * 4 > 64 * 1024 * 1024:
            raise ValueError("Image exceeds decode budget")
        decoded.format = 3  # PNG_FORMAT_RGBA
        pixels = bytearray(width * height * 4)
        output = (ctypes.c_char * len(pixels)).from_buffer(pixels)
        if not _LIBPNG.png_image_finish_read(pointer, None, output, 0, None):
            raise ValueError(decoded.message.decode("utf-8", "replace"))
        return width, height, pixels
    finally:
        _LIBPNG.png_image_free(pointer)

