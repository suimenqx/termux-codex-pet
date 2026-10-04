"""Current production Akita accessory coverage."""

from pathlib import Path
import unittest

from tools.historical_art import _decode_rgba_png


class CollarArtTests(unittest.TestCase):
    def test_every_current_akita_frame_keeps_the_blue_collar(self):
        root = Path(__file__).resolve().parents[1] / 'codex_pet/assets/akita/frames'
        paths = sorted(root.glob('*/*.png'))
        self.assertEqual(len(paths), 44)
        for path in paths:
            pixels = _decode_rgba_png(path.read_bytes())[2]
            blue_pixels = sum(
                1 for index in range(0, len(pixels), 4)
                if pixels[index + 3] > 0
                and pixels[index] < 80
                and pixels[index + 1] < 150
                and pixels[index + 2] > 120
                and pixels[index + 2] > pixels[index + 1]
            )
            self.assertGreater(blue_pixels, 50, path.as_posix())


if __name__ == '__main__':
    unittest.main()
