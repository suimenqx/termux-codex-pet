"""Pure drag state: normalized screen coordinates in, move/commit results out."""
from __future__ import annotations
from dataclasses import dataclass
from .renderer.protocol import TouchInput


@dataclass(frozen=True)
class DragResult:
    position: tuple[int, int] | None = None
    commit: bool = False


class DragController:
    def __init__(self, position: tuple[int, int], density: float) -> None:
        self.position = self.committed = position
        self.slop = 6 * density
        self.down: tuple[float, float, int, int, int, int] | None = None
        self.anchor: tuple[float, float] | None = None
        self.dragged = False

    def _anchor(self) -> None:
        if self.down is not None and self.anchor is not None:
            x, y, _, _, ox, oy = self.down
            self.down = (x, y, max(0, round(x - self.anchor[0])),
                         max(0, round(y - self.anchor[1])), ox, oy)

    def handle(self, event: TouchInput) -> DragResult:
        action, point = event.action, event.point
        if action == 'anchor':
            self.anchor = point
            self._anchor()
        elif action == 'down' and point is not None and self.down is None:
            self.down = (*point, *self.position, *self.position)
            self.dragged = False
            self._anchor()
        elif action == 'move' and point is not None and self.down is not None:
            dx, dy = point[0] - self.down[0], point[1] - self.down[1]
            self.dragged |= dx * dx + dy * dy > self.slop * self.slop
            if self.dragged:
                self.position = (max(0, self.down[2] + round(dx)),
                                 max(0, self.down[3] + round(dy)))
                return DragResult(self.position)
        elif action in ('up', 'cancel', 'screen_off'):
            result = DragResult()
            if action == 'up' and self.down is not None and self.dragged:
                self.committed = self.position
                result = DragResult(self.position, True)
            elif action != 'up' and self.position != self.committed:
                self.position = self.committed
                result = DragResult(self.position)
            self.down = self.anchor = None
            self.dragged = False
            return result
        return DragResult()
