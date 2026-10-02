"""Backend-neutral rendering contract: immutable, tightly packed straight RGBA8."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RgbaFrame:
    key: tuple
    width: int
    height: int
    pixels: bytes
    color_space: str = "srgb"
    alpha_mode: str = "straight"

    def __post_init__(self) -> None:
        if (type(self.width) is not int or type(self.height) is not int
                or min(self.width, self.height) <= 0 or not isinstance(self.pixels, bytes)
                or self.width * self.height * 4 > 64 * 1024 * 1024
                or self.color_space != "srgb" or self.alpha_mode != "straight"
                or len(self.pixels) != self.width * self.height * 4):
            raise ValueError('Frame requires positive dimensions and immutable packed RGBA bytes')
        hash(self.key)


class Renderer(Protocol):
    def present(self, frame: RgbaFrame) -> None: ...
    def move(self, x: int, y: int) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class TouchInput:
    action: str
    point: tuple[float, float] | None = None
