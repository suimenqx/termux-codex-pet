"""One native framebuffer owned for the entire lifetime of one connection."""
from __future__ import annotations
import fcntl
import mmap
import os
import stat
from .transport import Connection
from ..image_contract import rgba_size

ASHMEM_GET_SIZE = 0x7704


class SharedFramebuffer:
    def __init__(self, connection: Connection, width: int, height: int):
        self.c = connection
        self.size = 0
        self.dimensions = width, height
        self.fd: int | None = None
        self.mem: mmap.mmap | None = None
        self.closed = False
        try:
            self.size = rgba_size(width, height)
            self.bid, self.fd = connection.request_fd({'method': 'addBuffer',
                                                      'params': {'w': width, 'h': height, 'format': 'ARGB888'}})
            info = os.fstat(self.fd)
            capacity = info.st_size
            if stat.S_ISCHR(info.st_mode):
                # Android 12 ashmem is a character device with st_size == 0.
                capacity = fcntl.ioctl(self.fd, ASHMEM_GET_SIZE)
            elif not stat.S_ISREG(info.st_mode):
                raise ValueError('Unexpected shared-memory descriptor type')
            if capacity != self.size:
                raise ValueError(
                    'Shared-memory capacity differs from framebuffer')
            self.mem = mmap.mmap(self.fd, self.size, access=mmap.ACCESS_WRITE)
        except BaseException:
            self.close()
            raise

    def write(self, pixels: bytes) -> None:
        if self.closed or self.mem is None:
            raise RuntimeError('Framebuffer is closed')
        if len(pixels) != self.size:
            raise ValueError('Framebuffer requires tightly packed RGBA')
        self.mem[:] = pixels

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        # Never deleteBuffer while the native LocalSocket retains that FD.
        # Closing both channels retires all connection-scoped native objects.
        try:
            self.c.close()
        finally:
            try:
                if self.mem is not None:
                    self.mem.close()
                    self.mem = None
            finally:
                if self.fd is not None:
                    os.close(self.fd)
                    self.fd = None
