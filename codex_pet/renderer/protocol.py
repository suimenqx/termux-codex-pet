"""Backend-neutral rendering contract: immutable, tightly packed straight RGBA8."""
from dataclasses import dataclass
from typing import Protocol
from ..image_contract import rgba_size


@dataclass(frozen=True)
class RgbaFrame:
    key: tuple
    width: int
    height: int
    pixels: bytes
    color_space: str = "srgb"
    alpha_mode: str = "straight"

    def __post_init__(self) -> None:
        size = rgba_size(self.width, self.height)
        if (not isinstance(self.pixels, bytes)
                or self.color_space != "srgb" or self.alpha_mode != "straight"
                or len(self.pixels) != size):
            raise ValueError(
                'Frame requires positive dimensions and immutable packed RGBA bytes')
        hash(self.key)


class Renderer(Protocol):
    def present(self, frame: RgbaFrame) -> None: ...
    def move(self, x: int, y: int) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class TouchInput:
    action: str
    point: tuple[float, float] | None = None
