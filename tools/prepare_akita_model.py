#!/usr/bin/env python3
"""Build the fixed, shared Akita texture layers; requires tools/requirements-art.txt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "docs/artwork/akita/rig-v1"
TEXTURE_SCALE = 4


def resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return image.convert("RGBa").resize(size, Image.Resampling.LANCZOS).convert("RGBA")


def isolate(source: Image.Image, polygon: list[tuple[int, int]]) -> Image.Image:
    mask = Image.new("L", source.size)
    ImageDraw.Draw(mask).polygon([(x * TEXTURE_SCALE, y * TEXTURE_SCALE)
                                 for x, y in polygon], fill=255)
    result = source.copy()
    result.putalpha(ImageChops.multiply(source.getchannel("A"), mask))
    return result


def prepare() -> None:
    layers = MODEL_DIR / "layers"
    layers.mkdir(parents=True, exist_ok=True)
    reference = MODEL_DIR.parent / "2026-10-inbetweens/neutral-source.png"
    source = resize(Image.open(reference).convert("RGBA"), (1024, 1024))
    # The reference ears start at y~30. Exclude isolated alpha=1 generator
    # dust above y20 before rigging, while preserving the entire silhouette.
    head = isolate(source, [(100, 20), (256, 20), (256, 155), (203, 155),
                            (193, 151), (172, 149), (149, 145), (125, 139),
                            (108, 129), (98, 113), (99, 97)])
    # The blue collar belongs to the body, so it never rotates with the face.
    pixels = head.load()
    for y in range(135 * TEXTURE_SCALE, 158 * TEXTURE_SCALE):
        for x in range(115 * TEXTURE_SCALE, 230 * TEXTURE_SCALE):
            r, g, b, a = pixels[x, y]
            if b > r * 1.3 and b > g * 1.05:
                pixels[x, y] = (r, g, b, 0)
    head.save(layers / "head.png")
    collar = isolate(source, [(127, 137), (166, 141), (195, 138),
                              (201, 151), (181, 166), (145, 158), (127, 149)])
    collar.save(layers / "collar.png")
    tail = isolate(source, [(0, 58), (94, 58), (104, 87), (104, 129),
                            (83, 141), (49, 149), (0, 149)])
    tail.save(layers / "tail.png")

    atlas = Image.open(MODEL_DIR / "parts-source.png").convert("RGBA")
    # Measured component bounds of this static atlas, with an 8-source-pixel
    # filter/fur margin. These are bind-time crops, never per-frame framing.
    crops = {"body": (103, 113, 849, 616),
             "fore": (1040, 73, 1369, 643),
             "hind": (1659, 68, 1995, 638)}
    # The neutral reference's belly sits above the lower legs. Keeping that
    # anatomical line prevents the torso from hiding the entire stride.
    body_box = (38, 121, 199, 187)
    body = Image.new("RGBA", (1024, 1024))
    piece = resize(atlas.crop(crops["body"]),
                   ((body_box[2] - body_box[0]) * 4, (body_box[3] - body_box[1]) * 4))
    body.paste(piece, (body_box[0] * 4, body_box[1] * 4))
    body.save(layers / "body.png")
    for name, width in (("fore", 43), ("hind", 50)):
        limb = resize(atlas.crop(crops[name]), (width * 4, 110 * 4))
        # A soft attachment is buried inside the painted torso, not exposed
        # as a separate round shoulder cap in every pose.
        attachment = Image.new("L", limb.size, 255)
        draw = ImageDraw.Draw(attachment)
        for y in range(40 * 4):
            t = min(1.0, max(0.0, (y / 4 - 10) / 30))
            draw.line((0, y, limb.width, y), fill=round(255 * t * t * (3 - 2 * t)))
        limb.putalpha(ImageChops.multiply(limb.getchannel("A"), attachment))
        limb.save(layers / f"{name}.png")

    model = {
        "revision": "akita-rig-v1", "canvas": 256, "texture_scale": 4,
        "origin": [128, 236], "body_pivot": [119, 165],
        "ground_speed": 240.0, "running_period": .64,
        "head_pivot": [167, 144], "tail_pivot": [66, 134],
        "eyes": [{"center": [165, 90], "radius": [12, 12]},
                 {"center": [204, 96], "radius": [10, 11]}],
        "palette": {"idle": [45, 121, 191], "running": [45, 121, 191],
                    "needs_input": [215, 147, 44], "ready": [47, 150, 103],
                    "blocked": [195, 92, 110]},
        "limb_bind": {
            "fore": {"root": [21, 20], "knee": [21, 50], "ankle": [21, 84],
                     "paw": [27, 100], "sole": 110, "bend": 1},
            "hind": {"root": [25, 18], "knee": [25, 52], "ankle": [21, 86],
                     "paw": [28, 100], "sole": 110, "bend": -1}},
        "legs": {
            "hind_far": {"kind": "hind", "root": [99, 160], "paw": [101, 215],
                         "projection": .9, "shade": .86, "contact_phase": 0.0,
                         "stance": .28, "stride": 42, "lift": 24},
            "fore_far": {"kind": "fore", "root": [180, 160], "paw": [188, 215],
                         "projection": .9, "shade": .89, "contact_phase": .44,
                         "stance": .32, "stride": 46, "lift": 27},
            "hind_near": {"kind": "hind", "root": [72, 158], "paw": [64, 224],
                          "projection": 1.0, "shade": 1.0, "contact_phase": .10,
                          "stance": .28, "stride": 46, "lift": 28},
            "fore_near": {"kind": "fore", "root": [143, 162], "paw": [148, 224],
                          "projection": 1.0, "shade": 1.0, "contact_phase": .56,
                          "stance": .32, "stride": 50, "lift": 30}},
        "source": {"neutral": str(reference.relative_to(ROOT)),
                   "neutral_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
                   "parts": "parts-source.png", "parts_size": list(atlas.size),
                   "parts_sha256": hashlib.sha256((MODEL_DIR / "parts-source.png").read_bytes()).hexdigest(),
                   "part_crops": crops, "body_bind_box": body_box},
        "layers": {p.stem: {"file": f"layers/{p.name}",
                            "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                   for p in sorted(layers.glob("*.png"))},
    }
    # One virtual ground speed, projected through the fixed camera. Support
    # strokes are derived from duration, not independently tuned per limb.
    for leg in model["legs"].values():
        leg["stride"] = (model["ground_speed"] * model["running_period"]
                         * leg["stance"] * leg["projection"])
    (MODEL_DIR / "model.json").write_text(json.dumps(model, indent=2) + "\n")
    print(MODEL_DIR / "model.json")


if __name__ == "__main__":
    prepare()
