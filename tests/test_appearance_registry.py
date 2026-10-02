import struct
import unittest

from tools.historical_animation import AnimationTimeline, playback_frames
from tools.historical_art import icon
from codex_pet.pet_pack import bundled_pack
from codex_pet.pets import (
    APPEARANCES, APPEARANCE_BY_ID, DEFAULT_APPEARANCE, DEFAULT_APPEARANCE_SPEC,
    appearance_for,
)


class AppearanceRegistryTests(unittest.TestCase):
    def test_catalog_has_unique_ids_and_exactly_one_default(self) -> None:
        defaults = [appearance for appearance in APPEARANCES if appearance.is_default]

        self.assertEqual(len(APPEARANCE_BY_ID), len(APPEARANCES))
        self.assertEqual(len(defaults), 1)
        self.assertIs(defaults[0], DEFAULT_APPEARANCE_SPEC)
        self.assertEqual(DEFAULT_APPEARANCE, defaults[0].id)

    def test_every_appearance_resolves_art_dimensions_and_animation(self) -> None:
        for appearance in APPEARANCES:
            with self.subTest(appearance=appearance.id):
                pack = bundled_pack(appearance.id)
                image = icon("idle", appearance=appearance.id)
                dimensions = struct.unpack_from(">II", image, 16)
                self.assertEqual(
                    dimensions,
                    pack.canvas,
                )

                timeline = AnimationTimeline(appearance.id, "idle", now=0.0)
                schedule = playback_frames(appearance.id, "idle")
                self.assertEqual(schedule[0].frame, timeline.frame)

    def test_unknown_and_non_string_ids_resolve_to_the_default(self) -> None:
        self.assertIs(appearance_for("missing"), DEFAULT_APPEARANCE_SPEC)
        self.assertIs(appearance_for(None), DEFAULT_APPEARANCE_SPEC)


if __name__ == "__main__":
    unittest.main()
