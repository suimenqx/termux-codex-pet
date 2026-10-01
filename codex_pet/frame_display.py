"""Present artwork on the GUI thread with explicit native alpha ownership."""

from __future__ import annotations

from contextlib import suppress
import os

import termuxgui as tg

from .art import icon, premultiplied_icon
from .pets import ART_PROFILE_AKITA, PetAppearance


class FrameDisplay:
    """Own one reusable Akita buffer; other artwork uses its PNG decoder."""

    def __init__(self, connection: tg.Connection, face: tg.ImageView) -> None:
        self.connection = connection
        self.face = face
        self.buffer: tg.Buffer | None = None
        self.bound = False

    def show(self, appearance: PetAppearance, state: str, frame: int, count: int) -> None:
        if appearance.art_profile != ART_PROFILE_AKITA:
            self.face.setimage(icon(state, frame, count, appearance.id))
            self.bound = False
            return
        pixels = premultiplied_icon(state, frame, count)
        if self.buffer is None:
            size = appearance.image_size_px
            self.buffer = tg.Buffer(self.connection, size, size)
        self.buffer.mem[:] = pixels
        self.buffer.blit()
        if not self.bound:
            self.face.setbuffer(self.buffer)
            self.bound = True
        self.face.refresh()
        # This reply follows the native copy and invalidation on the same
        # ordered connection. Do not overwrite mapped pixels while the
        # previous blit may still be reading them. It is not a vsync signal.
        self.face.getdimensions()

    def close(self) -> None:
        """Release after the owner has detached/destroyed the ImageView."""
        buffer, self.buffer = self.buffer, None
        self.bound = False
        if buffer is None:
            return
        try:
            buffer.remove()
        except OSError:
            # The binding sends deleteBuffer before closing these resources;
            # a disconnected socket must not leak our mmap or file descriptor.
            with suppress(OSError, ValueError):
                buffer.mem.close()
            with suppress(OSError):
                os.close(buffer.fd)
            raise
