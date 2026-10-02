"""A GUI-owner byte LRU shared by source, composition and active encoding."""
from collections import OrderedDict
from dataclasses import dataclass

DEFAULT_BUDGET = 32 * 1024 * 1024


@dataclass(frozen=True)
class CacheStats:
    bytes_used: int
    budget: int
    entries: int
    hits: int
    misses: int
    evictions: int


class FrameCache:
    def __init__(self, budget: int = DEFAULT_BUDGET):
        if type(budget) is not int or budget < 0:
            raise ValueError('Cache budget must be a nonnegative integer')
        self.budget = budget
        self._entries: OrderedDict[tuple, tuple[bytes, bool]] = OrderedDict()
        self._bytes = self._hits = self._misses = self._evictions = 0

    def get(self, key: tuple) -> bytes | None:
        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        self._entries.move_to_end(key)
        return entry[0]

    def put(self, key: tuple, value: bytes, *, base: bool = False) -> bytes:
        if not isinstance(value, bytes):
            raise TypeError('Cache accepts immutable bytes only')
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._bytes -= len(previous[0])
        if not value or len(value) > self.budget:
            return value
        while self._bytes + len(value) > self.budget:
            # Derived frames and old encodings leave before decoded originals.
            victim = next((k for k, (_, is_base) in self._entries.items(
            ) if not is_base), next(iter(self._entries)))
            self._bytes -= len(self._entries.pop(victim)[0])
            self._evictions += 1
        self._entries[key] = (value, base)
        self._bytes += len(value)
        return value

    def discard_encoding(self, kind: str) -> None:
        for key in tuple(self._entries):
            if key[0] == kind:
                self._bytes -= len(self._entries.pop(key)[0])

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0

    def stats(self) -> CacheStats:
        return CacheStats(self._bytes, self.budget, len(self._entries), self._hits, self._misses, self._evictions)
