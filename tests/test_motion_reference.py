import unittest

import numpy as np

from tools.extract_motion_reference import clean_frame, merge_capture_samples


class MotionReferenceTests(unittest.TestCase):
    def test_capture_samples_merge_only_near_duplicates(self):
        base = np.zeros((4, 4, 3), dtype=np.uint8)
        almost = base.copy()
        almost[1, 1] = (2, 2, 2)
        changed = base.copy()
        changed[1, 1] = (100, 100, 100)
        groups = merge_capture_samples([base, almost, changed, changed.copy()], 5)
        self.assertEqual(groups, [[0, 1], [2, 3]])

    def test_capture_samples_reject_invalid_threshold_and_shapes(self):
        with self.assertRaises(ValueError):
            merge_capture_samples([np.zeros((1, 1, 3), dtype=np.uint8)], -1)
        with self.assertRaises(ValueError):
            merge_capture_samples(
                [np.zeros((1, 1, 3), dtype=np.uint8), np.zeros((2, 1, 3), dtype=np.uint8)]
            )

    def test_clean_frame_removes_dark_background_and_keeps_pet_pixels(self):
        rgb = np.zeros((3, 4, 3), dtype=np.uint8)
        rgb[:, :] = (9, 9, 12)
        rgb[1, 1] = (235, 125, 65)
        rgb[1, 2] = (245, 245, 240)
        rgba = clean_frame(rgb)
        self.assertEqual(tuple(rgba[0, 0]), (0, 0, 0, 0))
        self.assertGreater(int(rgba[1, 1, 3]), 200)
        self.assertGreater(int(rgba[1, 2, 3]), 200)
        self.assertEqual(rgba.shape, (3, 4, 4))


if __name__ == "__main__":
    unittest.main()
