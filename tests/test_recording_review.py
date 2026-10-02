import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_pet.art import _decode_rgba_png, _png
from tools.review_recording import (
    contact_sheet, crop_box, frame_table, media_environment, prepare,
    review_html, window_spec,
)


def probe(times):
    return {"streams": [{"codec_type": "video", "width": 32, "height": 24,
                         "start_time": "4.0", "duration": "1.2"}],
            "frames": [{"best_effort_timestamp_time": str(t)} for t in times]}


class RecordingReviewTests(unittest.TestCase):
    def test_variable_timestamps_are_preserved_without_inventing_frames(self):
        _, rows = frame_table(probe([4, 4.033, 4.12, 5]))
        self.assertEqual(len(rows), 4)
        self.assertEqual([r["frame"] for r in rows], list(range(4)))
        self.assertEqual([r["source_pts_seconds"] for r in rows], [4, 4.033, 4.12, 5])
        for value, expected in zip([r["duration_seconds"] for r in rows], [.033, .087, .88, .2]):
            self.assertAlmostEqual(value, expected)
        self.assertEqual(rows[0]["seconds"], 0)

    def test_invalid_or_reordered_timestamps_are_rejected(self):
        for times in ([], [4, 3], [float("nan")], [float("inf")]):
            with self.subTest(times=times), self.assertRaises(ValueError):
                frame_table(probe(times))

    def test_equal_timestamps_remain_in_source_order(self):
        _, rows = frame_table(probe([4, 4, 4.1]))
        self.assertEqual([r["frame"] for r in rows], [0, 1, 2])
        self.assertEqual(rows[0]["duration_seconds"], 0)

    def test_final_frame_duration_takes_precedence_over_stream_duration(self):
        data = probe([4, 4.5])
        data["frames"][-1]["duration_time"] = "0.08"
        self.assertEqual(frame_table(data)[1][-1]["duration_seconds"], .08)

    def test_crop_and_window_validation(self):
        self.assertEqual(crop_box("216,392,144,128"), (216, 392, 144, 128))
        self.assertEqual(window_spec("stop:23:26"), ("stop", 23, 26))
        for value in ("-1,0,1,1", "0,0,0,1", "0,0,1", "a,b,c,d"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                crop_box(value)
        for value in ("../bad:0:1", "index:0:1", "review:0:1", "a:nan:2", "a:1:1", "a:0:inf"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                window_spec(value)

    def test_media_environment_changes_only_child_library_settings(self):
        original = {"PREFIX": "/termux", "LD_PRELOAD": "old", "LD_LIBRARY_PATH": "old", "PATH": "bin"}
        with patch.object(Path, "is_file", return_value=True):
            child = media_environment(original)
        self.assertEqual(child, {"PREFIX": "/termux", "LD_LIBRARY_PATH": "/termux/lib", "PATH": "bin"})
        self.assertEqual(original["LD_PRELOAD"], "old")
        with patch.object(Path, "is_file", return_value=False):
            self.assertEqual(media_environment(original), original)

    def test_review_is_local_escaped_and_predecodes_before_playback(self):
        page = review_html([{"file": "frames/000000.png", "seconds": 0,
                             "duration_seconds": .1, "frame": 0}], "<script>bad</script>")
        self.assertIn("&lt;script&gt;bad&lt;/script&gt;", page)
        self.assertNotIn("fetch(", page)
        self.assertIn("img.decode()", page)
        self.assertIn("frames[index+1].seconds<=t", page)

    def test_contact_sheet_preserves_roi_pixels_and_source_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pixels = bytes((10, 20, 30, 255)) * 32 * 24
            (root / "one.png").write_bytes(_png(32, 24, bytearray(pixels)))
            image = contact_sheet([{"file": "one.png", "frame": 431, "seconds": 23.318989}], root)
            w, h, rgba = _decode_rgba_png(image)
            self.assertEqual(h, 42)
            for y in range(24):
                self.assertEqual(rgba[y*w*4:y*w*4+128], pixels[y*128:(y+1)*128])
            self.assertIn(bytes((240, 244, 249, 255)), rgba[24*w*4:])

    def test_existing_outputs_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "recording.mp4"
            source.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(source, root)
            self.assertEqual(source.read_bytes(), b"original")

    def test_end_to_end_manifest_and_atomic_failure_with_fake_decoder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "input.mp4", root / "review"
            source.write_bytes(b"untouched recording")

            def media(tool, arguments, env):
                if arguments == ["-version"]:
                    return f"{tool} fixture\n"
                if tool == "ffprobe":
                    return json.dumps(probe([4, 4.1, 5]))
                pattern = Path(arguments[-1])
                for i in range(3):
                    Path(str(pattern).replace("%06d", f"{i:06}")).write_bytes(
                        _png(8, 8, bytearray(bytes((1, 2, 3, 255)) * 64)))
                return ""

            with patch("tools.review_recording.run_media", side_effect=media):
                manifest = prepare(source, output, (0, 0, 8, 8), [("stop", .05, 1.1)])
            self.assertEqual(manifest["frame_count"], 3)
            self.assertEqual(manifest["windows"][0]["pages"][0]["frames"], [1, 2])
            self.assertTrue((output / "review.html").exists())
            self.assertFalse(manifest["audio_extracted"])
            self.assertEqual(source.read_bytes(), b"untouched recording")
            with patch("tools.review_recording.run_media", side_effect=[json.dumps(probe([4, 5])), ValueError("decode failed")]):
                with self.assertRaisesRegex(ValueError, "decode failed"):
                    prepare(source, root / "failed")
            self.assertFalse((root / "failed").exists())
            self.assertEqual(list(root.glob(".recording-review-*")), [])


if __name__ == "__main__":
    unittest.main()
