"""Lightweight catalog of shipped and locally imported pet appearances."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class PetAppearance:
    id: str
    name: str
    description: str
    is_default: bool = False


APPEARANCES = (
    PetAppearance(
        id="akita",
        name="Akita",
        description="An orange-red Akita with a round cream face and happy open mouth.",
        is_default=True,
    ),
    PetAppearance(
        id="robot",
        name="Robot",
        description="The original dark pixel robot.",
    ),
    PetAppearance(
        id="pixel_dog",
        name="Pixel Dog",
        description="A grey pixel dog with an original five-pose running loop (CC0).",
    ),
)
APPEARANCE_BY_ID = {appearance.id: appearance for appearance in APPEARANCES}

_DEFAULTS = tuple(appearance for appearance in APPEARANCES if appearance.is_default)
if len(APPEARANCE_BY_ID) != len(APPEARANCES):
    raise ValueError("Pet appearance IDs must be unique")
if len(_DEFAULTS) != 1:
    raise ValueError("Exactly one pet appearance must be the default")

DEFAULT_APPEARANCE_SPEC = _DEFAULTS[0]
DEFAULT_APPEARANCE = DEFAULT_APPEARANCE_SPEC.id


def local_pets_dir() -> Path:
    return Path.home() / '.local/share/codex-pet/pets'


def valid_local_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', value) is not None


@lru_cache(maxsize=8)
def _local_records(path: Path, modified: int, size: int) -> dict[str, PetAppearance]:
    if size > 65536:
        return {}
    try:
        records = json.loads(path.read_bytes())
        if not isinstance(records, dict):
            return {}
        found = {}
        for key, value in records.items():
            if not valid_local_id(key) or key in APPEARANCE_BY_ID or not isinstance(value, dict):
                continue
            name, description = value.get('name'), value.get('description', '')
            if (not isinstance(name, str) or not name or len(name) > 80
                    or not isinstance(description, str) or len(description) > 500
                    or any(ord(c) < 32 for c in name + description)):
                continue
            found[key] = PetAppearance(key, name, description)
        return found
    except (OSError, ValueError):
        return {}


def appearance_catalog() -> dict[str, PetAppearance]:
    """Read lightweight local metadata; never load images or a native backend."""
    result = dict(APPEARANCE_BY_ID)
    root = local_pets_dir()
    path = root / 'catalog.json'
    try:
        stat = path.stat()
        records = _local_records(path, stat.st_mtime_ns, stat.st_size)
        for key, value in records.items():
            folder = root / key
            if not folder.is_symlink() and (folder / 'pet.json').is_file():
                result[key] = value
    except OSError:
        pass
    return result


def appearance_for(appearance_id: object) -> PetAppearance:
    """Return the requested appearance, falling back safely to the default."""
    if isinstance(appearance_id, str):
        if appearance_id in APPEARANCE_BY_ID:
            return APPEARANCE_BY_ID[appearance_id]
        return appearance_catalog().get(appearance_id, DEFAULT_APPEARANCE_SPEC)
    return DEFAULT_APPEARANCE_SPEC
