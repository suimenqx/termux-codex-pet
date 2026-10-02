#!/usr/bin/env python3
"""Offline format experiment; never changes production assets or the daemon."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, features, __version__ as pillow_version
from codex_pet.pet_pack import bundled_pack
from codex_pet.image_codec import decode_png


def timed_decode(paths, repeats=7):
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        for path in paths:
            with Image.open(path) as image:
                with image.convert('RGBA') as rgba:
                    rgba.tobytes()
        samples.append((time.perf_counter() - start) * 1000)
    return {'samples_ms': samples, 'median_ms': statistics.median(samples)}


def probe():
    if not features.check('webp'):
        raise RuntimeError('This Pillow build has no WebP codec')
    pack = bundled_pack('akita')
    width, height = pack.canvas
    columns = 5
    rows = (len(pack.frames) + columns - 1) // columns
    atlas = Image.new('RGBA', (columns * width, rows * height))
    originals, references, paths = {}, {}, []
    for index, (reference, definition) in enumerate(pack.frames.items()):
        path = definition.file
        assert path is not None
        w, h, decoded = decode_png(path.read_bytes())
        assert (w, h) == (width, height)
        pixels = bytes(decoded)
        originals[reference] = pixels
        paths.append(path)
        x, y = index % columns * width, index // columns * height
        with Image.frombytes('RGBA', (width, height), pixels) as frame:
            # No mask: preserve straight alpha and hidden RGB exactly.
            atlas.paste(frame, (x, y))
        references[reference] = {
            'rect': [x, y, width, height],
            'rgba_sha256': hashlib.sha256(pixels).hexdigest(),
            'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    with tempfile.TemporaryDirectory(prefix='pet-atlas-') as temp:
        target = Path(temp) / 'atlas.webp'
        start = time.perf_counter()
        atlas.save(target, format='WEBP', lossless=True, exact=True,
                   quality=100, method=6)
        encode_ms = (time.perf_counter() - start) * 1000
        atlas.close()
        with Image.open(target) as encoded, encoded.convert('RGBA') as decoded:
            for reference, value in references.items():
                x, y, w, h = value['rect']
                with decoded.crop((x, y, x + w, y + h)) as frame:
                    assert frame.tobytes() == originals[reference], reference
        png_times, atlas_times = [], []
        # Alternate paired rounds; input files are OS-cache warm. This is not
        # cold startup, production PNG verification, or frame presentation.
        for order in ((False, True), (True, False)):
            for is_atlas in order:
                result = timed_decode([target] if is_atlas else paths)
                (atlas_times if is_atlas else png_times).append(result)
        result = {
            'pillow': pillow_version, 'libwebp': features.version('webp'),
            'pack_revision': pack.revision, 'frames': len(paths),
            'frame_px': [width, height],
            'atlas_px': [columns * width, rows * height],
            'png_bytes': sum(path.stat().st_size for path in paths),
            'webp_bytes': target.stat().st_size,
            'atlas_rgba_bytes': columns * width * rows * height * 4,
            'webp_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'encoding': {'lossless': True, 'exact': True, 'quality': 100, 'method': 6},
            'encode_ms': encode_ms, 'all_rgba_equal': True,
            'png_decode_rounds': png_times, 'webp_decode_rounds': atlas_times,
            'references': references,
            'limits': 'Offline codec experiment; no runtime migration, cold-start, RSS, Android display or native cleanup claim.',
        }
    # Explicitly exercise hidden RGB plus every alpha value, independently of
    # whether current artwork happens to contain nonzero fully transparent RGB.
    synthetic = bytes(channel for alpha in range(256)
                      for channel in (17, 99, 231, alpha))
    encoded = io.BytesIO()
    with Image.frombytes('RGBA', (256, 1), synthetic) as sample:
        sample.save(encoded, format='WEBP', lossless=True, exact=True)
    encoded.seek(0)
    with Image.open(encoded) as sample, sample.convert('RGBA') as rgba:
        assert rgba.tobytes() == synthetic
    result['all_alpha_values_and_hidden_rgb_equal'] = True
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = probe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({key: data[key] for key in (
        'pillow', 'libwebp', 'frames', 'png_bytes', 'webp_bytes',
        'atlas_rgba_bytes', 'all_rgba_equal', 'all_alpha_values_and_hidden_rgb_equal',
        'png_decode_rounds', 'webp_decode_rounds')}, indent=2))
