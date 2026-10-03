#!/usr/bin/env python3
"""Apply a generated high-resolution redraw under an original sprite alpha mask.

The source frame owns geometry: the generated RGB is allowed to contribute
surface detail, while the source alpha is restored exactly for the 256 px
candidate. This is a static spatial composite, never a temporal blend.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _resize_plane(plane: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray(np.clip(np.rint(plane), 0, 255).astype(np.uint8), "L")
    return np.asarray(image.resize(size, Image.Resampling.LANCZOS), dtype=np.float32)


def _premultiplied_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize straight-alpha RGBA without pulling transparent RGB into edges."""
    data = np.asarray(image.convert("RGBA"), dtype=np.float32)
    alpha = data[..., 3]
    premultiplied = data[..., :3] * (alpha[..., None] / 255.0)
    resized_alpha = _resize_plane(alpha, size)
    resized_premultiplied = np.stack(
        [_resize_plane(premultiplied[..., channel], size) for channel in range(3)],
        axis=-1,
    )
    rgb = np.zeros_like(resized_premultiplied)
    np.divide(
        resized_premultiplied * 255.0,
        np.maximum(resized_alpha[..., None], 1.0),
        out=rgb,
        where=resized_alpha[..., None] > 0,
    )
    rgb = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    alpha_u8 = np.clip(np.rint(resized_alpha), 0, 255).astype(np.uint8)
    output = np.dstack((rgb, alpha_u8))
    output[alpha_u8 == 0, :3] = 0
    return Image.fromarray(output, "RGBA")


def _locked_redraw(original: Image.Image, generated: Image.Image) -> Image.Image:
    """Use generated RGB at high resolution while locking original alpha."""
    original = original.convert("RGBA")
    generated = generated.convert("RGBA")
    mask = original.getchannel("A").resize(generated.size, Image.Resampling.LANCZOS)
    data = np.asarray(generated, dtype=np.uint8).copy()
    data[..., 3] = np.asarray(mask, dtype=np.uint8)
    data[data[..., 3] == 0, :3] = 0
    return Image.fromarray(data, "RGBA")


def _detail_only_redraw(original: Image.Image, generated: Image.Image) -> Image.Image:
    """Blend generated detail into an upscaled original, protecting the edge."""
    original = original.convert("RGBA")
    generated = generated.convert("RGBA")
    base = _premultiplied_resize(original, generated.size)
    mask = original.getchannel("A").resize(generated.size, Image.Resampling.LANCZOS)
    # Keep a two-source-pixel safety band around the original contour. A low
    # blend inside the core improves surface detail without importing a new
    # generated silhouette or limb boundary.
    core = mask.filter(ImageFilter.MinFilter(21))
    weight = np.asarray(core, dtype=np.float32)[..., None] / 255.0 * 0.30
    base_data = np.asarray(base, dtype=np.float32)
    generated_data = np.asarray(generated, dtype=np.float32)
    rgb = np.clip(
        np.rint(base_data[..., :3] * (1.0 - weight) + generated_data[..., :3] * weight),
        0,
        255,
    ).astype(np.uint8)
    alpha = np.asarray(mask, dtype=np.uint8)
    output = np.dstack((rgb, alpha))
    output[alpha == 0, :3] = 0
    return Image.fromarray(output, "RGBA")


def _with_background(image: Image.Image, color: tuple[int, int, int], size: int) -> Image.Image:
    canvas = Image.new("RGBA", image.size, (*color, 255))
    canvas.alpha_composite(image)
    return canvas.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)


def _comparison(original: Image.Image, candidate: Image.Image, output: Path) -> None:
    tile = 192
    label_height = 22
    sheet = Image.new("RGB", (tile * 2, (tile + label_height) * 2), (230, 230, 230))
    draw = ImageDraw.Draw(sheet)
    entries = (
        (original, (245, 245, 245), "original / light"),
        (candidate, (245, 245, 245), "locked / light"),
        (original, (38, 38, 42), "original / dark"),
        (candidate, (38, 38, 42), "locked / dark"),
    )
    for index, (image, background, label) in enumerate(entries):
        x = (index % 2) * tile
        y = (index // 2) * (tile + label_height)
        sheet.paste(_with_background(image, background, tile), (x, y))
        draw.rectangle((x, y + tile, x + tile, y + tile + label_height), fill=(230, 230, 230))
        draw.text((x + 5, y + tile + 4), label, fill=(20, 20, 20))
    sheet.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path, help="the 256 px source frame")
    parser.add_argument("generated", type=Path, help="the generated high-resolution redraw")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    original = Image.open(args.original).convert("RGBA")
    generated = Image.open(args.generated).convert("RGBA")
    if original.size != (256, 256):
        raise ValueError(f"expected a 256 x 256 source frame, got {original.size}")
    if generated.width != generated.height:
        raise ValueError(f"generated redraw must be square, got {generated.size}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    highres = _locked_redraw(original, generated)
    highres_path = args.output_dir / "fixed-alpha-redraw-running-00-1254.png"
    highres.save(highres_path)

    production = _premultiplied_resize(highres, original.size)
    # The production candidate's alpha is byte-for-byte the original mask.
    production.putalpha(original.getchannel("A"))
    production_path = args.output_dir / "fixed-alpha-redraw-running-00-256.png"
    production.save(production_path)

    comparison_path = args.output_dir / "fixed-alpha-compare-192px.png"
    _comparison(original, production, comparison_path)

    detail_highres = _detail_only_redraw(original, generated)
    detail_highres_path = args.output_dir / "fixed-detail-redraw-running-00-1254.png"
    detail_highres.save(detail_highres_path)
    detail_production = _premultiplied_resize(detail_highres, original.size)
    detail_production.putalpha(original.getchannel("A"))
    detail_production_path = args.output_dir / "fixed-detail-redraw-running-00-256.png"
    detail_production.save(detail_production_path)
    detail_comparison_path = args.output_dir / "fixed-detail-compare-192px.png"
    _comparison(original, detail_production, detail_comparison_path)

    print(f"highres={highres_path}")
    print(f"production={production_path}")
    print(f"comparison={comparison_path}")
    print(f"detail_highres={detail_highres_path}")
    print(f"detail_production={detail_production_path}")
    print(f"detail_comparison={detail_comparison_path}")
    print(f"alpha_equal={production.getchannel('A').tobytes() == original.getchannel('A').tobytes()}")
    print(f"detail_alpha_equal={detail_production.getchannel('A').tobytes() == original.getchannel('A').tobytes()}")
    print(f"original_bbox={original.getchannel('A').getbbox()}")
    print(f"production_bbox={production.getchannel('A').getbbox()}")


if __name__ == "__main__":
    main()
