import struct
import unittest

from codex_pet.animation import AnimationTimeline, playback_frames
from codex_pet.art import icon
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
                self.assertGreater(appearance.image_size_px, 0)
                image = icon("idle", appearance=appearance.id)
                dimensions = struct.unpack_from(">II", image, 16)
                self.assertEqual(
                    dimensions,
                    (appearance.image_size_px, appearance.image_size_px),
                )

                timeline = AnimationTimeline(appearance.id, "idle", now=0.0)
                schedule = playback_frames(appearance.id, "idle")
                self.assertEqual(schedule[0].frame, timeline.frame)
                self.assertTrue(appearance.art_profile)
                self.assertTrue(appearance.animation_profile)

    def test_unknown_and_non_string_ids_resolve_to_the_default(self) -> None:
        self.assertIs(appearance_for("missing"), DEFAULT_APPEARANCE_SPEC)
        self.assertIs(appearance_for(None), DEFAULT_APPEARANCE_SPEC)


if __name__ == "__main__":
    unittest.main()
