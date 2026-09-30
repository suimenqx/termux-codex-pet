"""Catalog of the pet appearances shipped with Codex Pet."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PetAppearance:
    id: str
    name: str
    description: str


DEFAULT_APPEARANCE = "akita"
APPEARANCES = (
    PetAppearance("akita", "Akita", "A compact red-and-cream Akita with a curled tail."),
    PetAppearance("robot", "Robot", "The original dark pixel robot."),
)
APPEARANCE_BY_ID = {appearance.id: appearance for appearance in APPEARANCES}
