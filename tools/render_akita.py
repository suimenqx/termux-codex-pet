#!/usr/bin/env python3
"""Bake all Akita clips from one layered rig. Pillow is an offline dependency."""

from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageChops, __version__ as PILLOW_VERSION  # noqa: E402

from codex_pet.animation import AKITA_FRAME_INTERVALS, AKITA_READY_LOOP_START  # noqa: E402
from codex_pet.art import _premultiply_rgba  # noqa: E402
from tools.akita_rig import (  # noqa: E402
    MODEL_PATH, clip_poses, load_model, pose_at, rigid, bone_point, smooth,
)


def inverse_affine(source: list[tuple[float, float]], target: list[tuple[float, float]]) -> tuple:
    """Map one destination triangle back into its source texture."""
    (x0, y0), (x1, y1), (x2, y2) = target
    dx1, dy1, dx2, dy2 = x1 - x0, y1 - y0, x2 - x0, y2 - y0
    determinant = dx1 * dy2 - dx2 * dy1
    if abs(determinant) < 1e-8:
        raise ValueError("degenerate skinning triangle")
    values = []
    for axis in (0, 1):
        u0, u1, u2 = (point[axis] for point in source)
        a = ((u1 - u0) * dy2 - (u2 - u0) * dy1) / determinant
        b = (dx1 * (u2 - u0) - dx2 * (u1 - u0)) / determinant
        values.extend((a, b, u0 - a * x0 - b * y0))
    return tuple(values)


class RigRenderer:
    def __init__(self, model_path: Path = MODEL_PATH, supersample: int = 2) -> None:
        self.model = load_model(model_path)
        self.scale = supersample
        self.size = self.model["canvas"] * supersample
        self.tex_scale = self.model["texture_scale"]
        self.layers = {}
        for name, metadata in self.model["layers"].items():
            path = model_path.parent / metadata["file"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
                raise ValueError(f"layer hash changed: {name}; rebuild model metadata")
            self.layers[name] = Image.open(path).convert("RGBA")

    @lru_cache(maxsize=16)
    def collar_texture(self, state: str) -> Image.Image:
        result = self.layers["collar"].copy()
        if state in ("idle", "running"):
            return result
        target = self.model["palette"][state]
        pixels = result.load()
        for y in range(110 * self.tex_scale, 166 * self.tex_scale):
            for x in range(110 * self.tex_scale, 210 * self.tex_scale):
                r, g, b, a = pixels[x, y]
                if a and b > r * 1.3 and b > g * 1.08:
                    value = b / 191
                    pixels[x, y] = (*[min(255, round(c * value)) for c in target], a)
        return result

    @lru_cache(maxsize=32)
    def head_texture(self, closure: float) -> Image.Image:
        result = self.layers["head"].copy()
        if closure < 1e-6:
            return result
        scale = self.tex_scale
        for eye in self.model["eyes"]:
            cx, cy = eye["center"]
            rx, ry = eye["radius"]
            outer_x, outer_y = rx * 1.6, ry * 1.6
            left, top = math.floor((cx - outer_x) * scale), math.floor((cy - outer_y) * scale)
            right, bottom = math.ceil((cx + outer_x) * scale), math.ceil((cy + outer_y) * scale)
            source = result.crop((left, top, right, bottom)).convert("RGBa")

            def lookup(x: float, y: float) -> tuple[float, float]:
                wx, wy = (x + left) / scale, (y + top) / scale
                weight = smooth((outer_x - abs(wx - cx)) / (outer_x - rx))
                factor = 1 - .94 * closure * weight
                center = cy + 1.5 * closure * weight
                inner = ry * .70
                dy = wy - center
                if abs(dy) <= inner * factor:
                    mapped = cy + dy / factor
                elif dy < 0:
                    mapped = cy - inner + (dy + inner * factor) * (outer_y - inner) / (outer_y - inner * factor)
                else:
                    mapped = cy + inner + (dy - inner * factor) * (outer_y - inner) / (outer_y - inner * factor)
                # Taper the lid's shift to zero at the crop boundary as well.
                taper = smooth((outer_y - abs(wy - cy)) / (outer_y - ry))
                mapped = wy + (mapped - wy) * taper
                return x, mapped * scale - top

            mesh = []
            for y in range(0, source.height, 4):
                for x in range(0, source.width, 4):
                    x1, y1 = min(x + 4, source.width), min(y + 4, source.height)
                    quad = (*lookup(x, y), *lookup(x, y1), *lookup(x1, y1), *lookup(x1, y))
                    mesh.append(((x, y, x1, y1), quad))
            warped = source.transform(source.size, Image.Transform.MESH, mesh,
                                      Image.Resampling.BILINEAR).convert("RGBA")
            result.paste(warped, (left, top))
            if closure > .6:
                # The compressed iris becomes subpixel at the native size.
                # A lid stroke keeps the same closed-eye curve readable.
                lid = Image.new("RGBA", result.size)
                points = [((cx + rx * .7 * i / 8) * scale,
                           (cy + 1.5 + 1.4 * ((i / 8) ** 2 - 1)) * scale)
                          for i in range(-8, 9)]
                ImageDraw.Draw(lid).line(points, fill=(61, 34, 24,
                    round(255 * smooth((closure - .6) / .4))), width=round(1.4 * scale))
                result = Image.alpha_composite(result, lid)
        return result

    def rigid_layer(self, image: Image.Image, pivot: list, transform: dict) -> Image.Image:
        # Both raster coordinates include pixel centers; one affine preserves
        # registration for every state, with no state-dependent scale.
        if transform["scale"] != 1.0:
            raise ValueError("rig-v1 forbids state-dependent head/body/tail scale")
        target = [rigid(p, pivot, transform["offset"], transform["angle"])
                  for p in ((0, 0), (256, 0), (0, 256))]
        target = [(x * self.scale, y * self.scale) for x, y in target]
        source = [(0, 0), (256 * self.tex_scale, 0), (0, 256 * self.tex_scale)]
        matrix = inverse_affine(source, target)
        return image.convert("RGBa").transform((self.size, self.size), Image.Transform.AFFINE,
                                               matrix, Image.Resampling.BICUBIC).convert("RGBA")

    @lru_cache(maxsize=12)
    def limb_patch(self, name: str, bone: int) -> Image.Image:
        config = self.model["legs"][name]
        kind = config["kind"]
        texture = self.layers[kind].copy()
        bind = self.model["limb_bind"][kind]
        knee, ankle = bind["knee"][1], bind["ankle"][1]
        mask = Image.new("L", texture.size)
        draw = ImageDraw.Draw(mask)
        for row in range(texture.height):
            y = row / self.tex_scale
            if bone == 0:
                coverage = 1 - smooth((y - (knee - 2)) / 14)
            elif bone == 1:
                coverage = smooth((y - (knee - 12)) / 16) * (1 - smooth((y - (ankle - 4)) / 16))
            else:
                coverage = smooth((y - (ankle - 12)) / 15)
            draw.line((0, row, texture.width, row), fill=round(255 * coverage))
        texture.putalpha(ImageChops.multiply(texture.getchannel("A"), mask))
        if config["shade"] != 1:
            r, g, b, alpha = texture.split()
            shade = config["shade"]
            texture = Image.merge("RGBA", (r.point(lambda v: round(v * shade)),
                                          g.point(lambda v: round(v * shade)),
                                          b.point(lambda v: round(v * shade)), alpha))
        return texture.convert("RGBa")

    def limb_layer(self, name: str, pose: dict) -> Image.Image:
        kind = self.model["legs"][name]["kind"]
        bind = self.model["limb_bind"][kind]
        output = Image.new("RGBA", (self.size, self.size))
        for bone in range(3):
            texture = self.limb_patch(name, bone)
            world = [(0, 0), (texture.width / self.tex_scale, 0),
                     (0, texture.height / self.tex_scale)]
            target = [bone_point(point, bind, pose, bone) for point in world]
            target = [(x * self.scale, y * self.scale) for x, y in target]
            source = [(x * self.tex_scale, y * self.tex_scale) for x, y in world]
            matrix = inverse_affine(source, target)
            part = texture.transform((self.size, self.size), Image.Transform.AFFINE,
                                     matrix, Image.Resampling.BICUBIC).convert("RGBA")
            output = Image.alpha_composite(output, part)
        return output

    def render(self, pose: dict) -> tuple[Image.Image, dict]:
        parts = [(name, self.limb_layer(name, pose["legs"][name]))
                 for name in ("hind_far", "fore_far")]
        parts.append(("tail", self.rigid_layer(self.layers["tail"], self.model["tail_pivot"], pose["tail"])))
        parts.append(("body", self.rigid_layer(self.layers["body"], self.model["body_pivot"], pose["body"])))
        parts.extend((name, self.limb_layer(name, pose["legs"][name]))
                     for name in ("hind_near", "fore_near"))
        parts.extend([
            ("collar", self.rigid_layer(self.collar_texture(pose["state"]), self.model["body_pivot"], pose["body"])),
        ])
        parts.append(("head", self.rigid_layer(self.head_texture(round(pose["blink"], 5)),
                                                self.model["head_pivot"], pose["head"])))
        canvas = Image.new("RGBA", (self.size, self.size))
        for _, part in parts:
            canvas = Image.alpha_composite(canvas, part)
        visibility = {}
        for index, (name, part) in enumerate(parts):
            if name not in pose["legs"]:
                continue
            px, py = pose["legs"][name]["paw"]
            samples = []
            for dy in (-2, 0, 2):
                for dx in (-2, 0, 2):
                    x, y = round((px + dx) * self.scale), round((py + dy) * self.scale)
                    coverage = part.getpixel((x, y))[3] / 255
                    for _, covering in parts[index + 1:]:
                        coverage *= 1 - covering.getpixel((x, y))[3] / 255
                    samples.append(coverage)
            visibility[name] = sum(samples) / len(samples)
        result = canvas.convert("RGBa").resize((256, 256), Image.Resampling.LANCZOS).convert("RGBA")
        return result, visibility


def png_bytes(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=9)
    return stream.getvalue()


def export(output: Path, states: list[str], model_path: Path = MODEL_PATH) -> dict:
    renderer = RigRenderer(model_path)
    output.mkdir(parents=True, exist_ok=True)
    native_frames = {}
    manifest = {"model": renderer.model["revision"],
                "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                "authoring_sha256": {name: hashlib.sha256((ROOT / "tools" / name).read_bytes()).hexdigest()
                                     for name in ("prepare_akita_model.py", "akita_rig.py", "render_akita.py")},
                "renderer": "fixed bones, overlapping rigid skin patches, eye mesh, premultiplied alpha",
                "pillow_version": PILLOW_VERSION, "supersample": renderer.scale,
                "head_scale": 1.0, "clips": {}}
    for state in states:
        directory = output / "frames" / state
        directory.mkdir(parents=True, exist_ok=True)
        poses = clip_poses(renderer.model, state)
        for path in directory.glob("*.png"):
            if path.name not in {f"{i:02}.png" for i in range(len(poses))}:
                path.unlink()
        metadata = []
        for pose in poses:
            image, visibility = renderer.render(pose)
            alpha = image.getchannel("A")
            if any(alpha.crop(box).getextrema()[1] for box in
                   ((0, 0, 256, 1), (0, 255, 256, 256), (0, 0, 1, 256), (255, 0, 256, 256))):
                raise ValueError(f"{state} frame {pose['frame']}: artwork touches canvas edge")
            data = png_bytes(image)
            filename = f"frames/{state}/{pose['frame']:02}.png"
            (output / filename).write_bytes(data)
            if pose["frame"] == 0:
                (output / f"{state}.png").write_bytes(data)
            for name, fraction in visibility.items():
                pose["legs"][name]["visible_fraction"] = fraction
            native = _premultiply_rgba(image.tobytes())
            native_frames[f"{state}/{pose['frame']:02}.rgba"] = native
            metadata.append({"file": filename, "sha256": hashlib.sha256(data).hexdigest(),
                             "native_rgba_sha256": hashlib.sha256(native).hexdigest(),
                             "rgba_sha256": hashlib.sha256(image.tobytes()).hexdigest(), **pose})
        manifest["clips"][state] = {"frames": metadata,
                                    "loop_start": AKITA_READY_LOOP_START if state == "ready" else 0,
                                    "final_hold": "until_state_change" if state == "blocked" else None}
        (output / f"preview-{state}.json").write_text(json.dumps({"frames": [
            {"file": frame["file"], "seconds": frame["seconds"]} for frame in metadata]}, indent=2) + "\n")
        print(f"{state}: {len(metadata)} poses, {sum(p['seconds'] for p in metadata):.3f}s", flush=True)
    archive_path = output / 'native-frames.zip'
    with ZipFile(archive_path, 'w') as archive:
        for filename, native in native_frames.items():
            # Fixed date and permissions make the derived transport artifact
            # reproducible; it never becomes an independent drawing source.
            entry = ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = 0o600 << 16
            archive.writestr(entry, native, compress_type=ZIP_DEFLATED, compresslevel=6)
    manifest['native_archive'] = {
        'file': archive_path.name, 'format': 'premultiplied RGBA8', 'size': [256, 256],
        'sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
    }
    (output / "rig-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state", choices=tuple(AKITA_FRAME_INTERVALS))
    parser.add_argument("--pose", type=float, help="render just this time, in seconds")
    args = parser.parse_args()
    if args.pose is not None:
        renderer = RigRenderer()
        pose = pose_at(renderer.model, args.state or "idle", args.pose)
        image, _ = renderer.render(pose)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(png_bytes(image))
    else:
        export(args.output, [args.state] if args.state else list(AKITA_FRAME_INTERVALS))


if __name__ == "__main__":
    main()
