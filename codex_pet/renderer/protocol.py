"""Backend-neutral rendering contract: immutable, tightly packed straight RGBA8."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RgbaFrame:
    key: tuple
    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        if (type(self.width) is not int or type(self.height) is not int
                or min(self.width, self.height) <= 0 or not isinstance(self.pixels, bytes)
                or len(self.pixels) != self.width * self.height * 4):
            raise ValueError('Frame requires positive dimensions and immutable packed RGBA bytes')
        hash(self.key)


class Renderer(Protocol):
    def present(self, frame: RgbaFrame) -> None: ...
    def move(self, x: int, y: int) -> None: ...
    def close(self) -> None: ...
