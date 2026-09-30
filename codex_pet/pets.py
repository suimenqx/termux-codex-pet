"""Catalog of the pet appearances shipped with Codex Pet."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PetAppearance:
    id: str
    name: str
    description: str
    image_size_px: int
    art_profile: str
    animation_profile: str
    is_default: bool = False


ART_PROFILE_AKITA = "akita"
ART_PROFILE_ROBOT = "robot"
ANIMATION_PROFILE_AKITA = "akita"
ANIMATION_PROFILE_ROBOT = "robot"

APPEARANCES = (
    PetAppearance(
        id="akita",
        name="Akita",
        description="An orange-red Akita with a round cream face and happy open mouth.",
        image_size_px=256,
        art_profile=ART_PROFILE_AKITA,
        animation_profile=ANIMATION_PROFILE_AKITA,
        is_default=True,
    ),
    PetAppearance(
        id="robot",
        name="Robot",
        description="The original dark pixel robot.",
        image_size_px=64,
        art_profile=ART_PROFILE_ROBOT,
        animation_profile=ANIMATION_PROFILE_ROBOT,
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


def appearance_for(appearance_id: object) -> PetAppearance:
    """Return the requested appearance, falling back safely to the default."""
    if isinstance(appearance_id, str):
        return APPEARANCE_BY_ID.get(appearance_id, DEFAULT_APPEARANCE_SPEC)
    return DEFAULT_APPEARANCE_SPEC
