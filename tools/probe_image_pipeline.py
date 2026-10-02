#!/usr/bin/env python3
"""Measure offline frame preparation without modifying assets or contacting GUI.

Run with --deps-root PATH pointing at a directory populated by ``dpkg-deb -x``
to test Termux packages without installing them globally. Generated atlases and
full samples go to the private cache. --output optionally writes a small report.
Timings concern Python preparation only, never Android presentation or power.
"""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
import mmap
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def summary(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "samples": len(samples),
        "median_ms": round(statistics.median(samples), 6),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 6),
        "min_ms": round(min(samples), 6),
    }


def measure(fn, samples: int, *, warmups: int = 2, batch: int = 1) -> list[float]:
    for _ in range(warmups):
        fn()
    result = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        for _ in range(batch):
            fn()
        result.append((time.perf_counter_ns() - start) / 1e6 / batch)
    return result


def premultiply_integer(pixels: bytes) -> bytes:
    output = bytearray(pixels)
    for i in range(0, len(output), 4):
        alpha = output[i + 3]
        output[i] = (output[i] * alpha + 127) // 255
        output[i + 1] = (output[i + 1] * alpha + 127) // 255
        output[i + 2] = (output[i + 2] * alpha + 127) // 255
    return bytes(output)


def child_measurements(imports: dict[str, str], repetitions: int) -> dict:
    result = {}
    for label, statement in imports.items():
        samples = []
        for _ in range(repetitions):
            code = (
                "import json,time; "
                "rss=lambda:int(next(s for s in open('/proc/self/status') if s.startswith('VmRSS:')).split()[1]); "
                "before=rss(); t=time.perf_counter_ns(); "
                + statement
                + "; print(json.dumps({'import_ms':(time.perf_counter_ns()-t)/1e6,"
                "'rss_before_kib':before,'rss_after_kib':rss()}))"
            )
            start = time.perf_counter_ns()
            child = subprocess.run(
                [sys.executable, "-c", code], text=True,
                capture_output=True, check=True, cwd=REPO,
            )
            sample = json.loads(child.stdout)
            sample["process_wall_ms"] = (time.perf_counter_ns() - start) / 1e6
            samples.append(sample)
        result[label] = {
            "import": summary([x["import_ms"] for x in samples]),
            "process_wall": summary([x["process_wall_ms"] for x in samples]),
            "rss_before_median_kib": statistics.median(x["rss_before_kib"] for x in samples),
            "rss_after_median_kib": statistics.median(x["rss_after_kib"] for x in samples),
            "rss_increase_median_kib": statistics.median(x["rss_after_kib"] - x["rss_before_kib"] for x in samples),
            "raw": samples,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deps-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/codex-pet/refactor-research/images")
    args = parser.parse_args()
    if args.samples < 5:
        parser.error("--samples must be at least 5")
    if args.deps_root and not os.environ.get("CODEX_PET_IMAGE_PROBE_DEPS"):
        prefix = args.deps_root.resolve() / "data/data/com.termux/files/usr"
        site = prefix / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(site) + os.pathsep + env.get("PYTHONPATH", "")
        env["LD_LIBRARY_PATH"] = str(prefix / "lib") + os.pathsep + env.get("LD_LIBRARY_PATH", "/data/data/com.termux/files/usr/lib")
        env["CODEX_PET_IMAGE_PROBE_DEPS"] = str(args.deps_root.resolve())
        os.execve(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env)

    from codex_pet import art

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Offline Python image preparation only; no GUI, Android frame, power, or thermal measurement.",
        "method": {
            "decode": "Resident encoded bytes, uncached decoded result; OS disk caches are NOT flushed.",
            "timing": "perf_counter_ns wall time, 2 warmups, serial measurements; no CPU governor control.",
            "copy": "Anonymous mmap, same Python buffer interface as termuxgui.Buffer.mem; NOT Android shared memory.",
            "384x416": "Unscaled production 256x256 frame pasted in a transparent test canvas; no new artwork.",
            "startup": "Fresh processes, warm OS caches; VmRSS from /proc/self/status before/after import, not inherited resource.ru_maxrss.",
        },
        "environment": {
            "python": sys.version,
            "machine": platform.machine(),
            "platform": platform.platform(),
            "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
            "isolated_deps": os.environ.get("CODEX_PET_IMAGE_PROBE_DEPS"),
        },
        "checks": {}, "timings": {}, "raw_timings": {},
    }
    import PIL
    result["environment"]["production_codec"] = "Pillow " + PIL.__version__
    result["method"]["baseline_note"] = (
        "Current production codec is Pillow. The Pillow/production comparison is not an independent codec oracle; "
        "use the committed pre-refactor RGBA fingerprints for migration validation. Historical libpng results remain archived.")
    # -I ignores PYTHONPATH and records current global dependency availability.
    result["environment"]["global_modules"] = json.loads(subprocess.check_output([
        sys.executable, "-I", "-c",
        "import json,importlib.util; print(json.dumps({m:bool(importlib.util.find_spec(m)) for m in ('PIL','numpy')}))",
    ], text=True))
    if args.deps_root:
        packages = []
        for path in sorted((args.deps_root.parent / "debs").glob("*.deb")):
            fields = subprocess.check_output([
                "dpkg-deb", "--field", str(path), "Package", "Version", "Installed-Size", "Depends",
            ], text=True)
            packages.append({
                "file": path.name, "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "control_fields": fields.strip(),
            })
        result["environment"]["downloaded_packages"] = packages
        result["environment"]["apt_simulated_install"] = subprocess.check_output([
            "apt-get", "-s", "install", "python-pillow", "python-numpy",
        ], text=True)
        without_native = os.environ.copy()
        without_native["LD_LIBRARY_PATH"] = "/data/data/com.termux/files/usr/lib"
        controls = {}
        for module in ("PIL.Image", "numpy"):
            child = subprocess.run(
                [sys.executable, "-c", f"import {module}"],
                capture_output=True, text=True, env=without_native,
            )
            controls[module] = {"returncode": child.returncode, "stderr": child.stderr}
        result["environment"]["control_imports_without_isolated_native_library_path"] = controls

    def bench(label, fn, *, batch=1, samples=None):
        raw = measure(fn, samples or args.samples, batch=batch)
        result["raw_timings"][label] = raw
        result["timings"][label] = summary(raw)

    sources = sorted((art.AKITA_ASSET_DIR / "frames").glob("*/*.png"))
    source_bytes = [p.read_bytes() for p in sources]
    decoded = [art._decode_rgba_png(b) for b in source_bytes]
    assert len(sources) == 34 and all(d[:2] == (256, 256) for d in decoded)
    result["sources"] = {
        "count": len(sources), "total_png_bytes": sum(map(len, source_bytes)),
        "sha256": {str(p.relative_to(REPO)): hashlib.sha256(b).hexdigest() for p, b in zip(sources, source_bytes)},
    }
    sample_bytes = source_bytes[0]
    sample_rgba = bytes(decoded[0][2])
    bench("production_decode_one_256", lambda: art._decode_rgba_png(sample_bytes))
    bench("production_decode_all_34", lambda: [art._decode_rgba_png(b) for b in source_bytes], samples=10)
    bench("stdlib_premultiply_256", lambda: premultiply_integer(sample_rgba), samples=10)
    art.rgba_icon("running", 0)
    art.icon("running", 0)
    bench("production_cached_rgba_lookup", lambda: art.rgba_icon("running", 0), batch=200)
    bench("production_cached_png_lookup", lambda: art.icon("running", 0), batch=200)
    cache_lookup = {0: sample_rgba}
    bench("prepared_bytes_dict_lookup", lambda: cache_lookup[0], batch=200)

    available = {name: importlib.util.find_spec(name) is not None for name in ("PIL", "numpy")}
    result["environment"]["modules_found"] = available
    imports = {"baseline": "pass", "production_art": "import codex_pet.art", "termuxgui": "import termuxgui"}
    for width, height in ((256, 256), (384, 416)):
        nbytes = width * height * 4
        memory = mmap.mmap(-1, nbytes)
        frame = sample_rgba if width == 256 else bytes(nbytes)
        bench(f"mmap_copy_bytes_{width}x{height}", lambda: memory.__setitem__(slice(None), frame), batch=100)
        assert memory[:] == frame
        memory.close()

    if available["PIL"]:
        import PIL
        from PIL import Image, features

        result["environment"]["pillow"] = PIL.__version__
        result["environment"]["pillow_features"] = {
            name: {"available": features.check(name), "version": features.version(name)}
            for name in ("webp", "zlib", "jpg", "jpg_2000", "libtiff", "raqm", "libimagequant")
        }
        imports["pillow_image"] = "from PIL import Image"
        frames = [Image.open(io.BytesIO(b)).convert("RGBA") for b in source_bytes]
        result["checks"]["pillow_production_all_frames_exact"] = all(im.tobytes() == bytes(d[2]) for im, d in zip(frames, decoded))
        bench("pillow_decode_one_256", lambda: Image.open(io.BytesIO(sample_bytes)).convert("RGBA").tobytes())
        bench("pillow_decode_all_34", lambda: [Image.open(io.BytesIO(b)).convert("RGBA").tobytes() for b in source_bytes], samples=10)

        columns = 6
        atlas = Image.new("RGBA", (columns * 256, math.ceil(len(frames) / columns) * 256))
        for index, im in enumerate(frames):
            atlas.paste(im, ((index % columns) * 256, (index // columns) * 256))
        atlas_pixels = atlas.tobytes()
        atlas_paths = {}
        result["atlases"] = {}
        for label, fmt, options in (
            ("png", "PNG", {}),
            ("webp_lossless_default", "WEBP", {"lossless": True}),
            ("webp_lossless_exact", "WEBP", {"lossless": True, "exact": True}),
        ):
            path = args.cache_dir / (label + (".png" if fmt == "PNG" else ".webp"))
            start = time.perf_counter_ns()
            atlas.save(path, format=fmt, **options)
            encode_ms = (time.perf_counter_ns() - start) / 1e6
            encoded = path.read_bytes()
            roundtrip = Image.open(io.BytesIO(encoded)).convert("RGBA").tobytes()
            changed_bytes = sum(a != b for a, b in zip(roundtrip, atlas_pixels))
            visible_changed = sum(
                roundtrip[i:i + 4] != atlas_pixels[i:i + 4]
                for i in range(0, len(roundtrip), 4) if atlas_pixels[i + 3]
            )
            result["atlases"][label] = {
                "path": str(path), "size_bytes": len(encoded), "encode_once_ms": encode_ms,
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "raw_rgba_exact": roundtrip == atlas_pixels,
                "changed_bytes": changed_bytes, "nonzero_alpha_changed_pixels": visible_changed,
            }
            atlas_paths[label] = path
            bench(label + "_atlas_decode", lambda data=encoded: Image.open(io.BytesIO(data)).convert("RGBA").tobytes(), samples=10)

        # Include hidden RGB explicitly: some production art may have cleared it.
        hidden_rgb = Image.frombytes("RGBA", (2, 1), bytes((255, 77, 33, 0, 99, 55, 11, 128)))
        result["checks"]["webp_hidden_rgb"] = {}
        for exact in (False, True):
            stream = io.BytesIO()
            hidden_rgb.save(stream, format="WEBP", lossless=True, exact=exact)
            output = Image.open(io.BytesIO(stream.getvalue())).convert("RGBA").tobytes()
            result["checks"]["webp_hidden_rgb"][str(exact)] = {"exact": output == hidden_rgb.tobytes(), "output": list(output)}

        sample_image = frames[0]
        exhaustive = bytes(v for alpha in range(256) for color in range(256) for v in (color, color, color, alpha))
        exhaustive_im = Image.frombytes("RGBA", (256, 256), exhaustive)
        reference = premultiply_integer(exhaustive)
        pillow_reference = exhaustive_im.convert("RGBa").tobytes()
        result["checks"]["pillow_premultiply_all_alpha_color_pairs_exact"] = pillow_reference == reference
        for width, height in ((256, 256), (384, 416)):
            im = sample_image if width == 256 else Image.new("RGBA", (width, height))
            if width != 256:
                im.paste(sample_image, (0, 0))
            bench(f"pillow_premultiply_{width}x{height}", lambda: im.convert("RGBa").tobytes())

        def predecode_prepare(label):
            image = Image.open(atlas_paths[label]).convert("RGBA")
            return [image.crop(((i % columns) * 256, (i // columns) * 256, (i % columns + 1) * 256, (i // columns + 1) * 256)).convert("RGBa").tobytes() for i in range(len(frames))]

        for label in ("png", "webp_lossless_exact"):
            bench(label + "_atlas_prepare_all_34_premultiplied_bytes", lambda key=label: predecode_prepare(key), samples=10)
            ready = predecode_prepare(label)
            result["checks"][label + "_prepared_frames_match"] = all(data == frame.convert("RGBa").tobytes() for data, frame in zip(ready, frames))

        if available["numpy"]:
            import numpy as np

            result["environment"]["numpy"] = np.__version__
            imports["numpy"] = "import numpy"
            imports["pillow_numpy"] = "from PIL import Image; import numpy"

            def numpy_premultiply(raw):
                array = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 4)
                converted = array.copy()
                converted[:, :3] = ((array[:, :3].astype(np.uint16) * array[:, 3:4] + 127) // 255).astype(np.uint8)
                return converted.tobytes()

            result["checks"]["numpy_premultiply_all_alpha_color_pairs_exact"] = numpy_premultiply(exhaustive) == reference
            for width, height in ((256, 256), (384, 416)):
                raw = sample_rgba if width == 256 else Image.new("RGBA", (width, height)).tobytes()
                bench(f"numpy_premultiply_{width}x{height}", lambda: numpy_premultiply(raw))
            array = np.asarray(atlas)
            crop = array[:256, 256:512, :]
            memory = mmap.mmap(-1, 256 * 256 * 4)
            try:
                memory[:] = crop
                direct_result = "accepted"
            except (BufferError, TypeError, ValueError) as exc:
                direct_result = f"{type(exc).__name__}: {exc}"
            contiguous = np.ascontiguousarray(crop)
            memory[:] = contiguous
            result["checks"]["numpy_atlas_crop"] = {
                "atlas_shape": list(array.shape), "crop_strides": list(crop.strides),
                "crop_c_contiguous": bool(crop.flags.c_contiguous),
                "direct_mmap_assignment": direct_result,
                "contiguous_assignment_exact": memory[:] == frames[1].tobytes(),
                "view_keeps_atlas_bytes_alive": array.nbytes,
            }
            bench("numpy_crop_tobytes_256", crop.tobytes)
            bench("numpy_crop_ascontiguous_256", lambda: np.ascontiguousarray(crop))
            bench("numpy_contiguous_mmap_copy_256", lambda: memory.__setitem__(slice(None), contiguous), batch=100)
            memory.close()

    result["fresh_processes"] = child_measurements(imports, 7)
    result["memory_calculations"] = {
        f"{w}x{h}": {
            "frame_bytes": w * h * 4,
            "34_frames_mib": w * h * 4 * 34 / 1024**2,
            "100_frames_mib": w * h * 4 * 100 / 1024**2,
            "80_entry_rgba_cache_mib": w * h * 4 * 80 / 1024**2,
            "single_copy_10fps_mib_s": w * h * 4 * 10 / 1024**2,
        } for w, h in ((256, 256), (384, 416))
    }
    full_path = args.cache_dir / "image-results-full.json"
    full_path.write_text(json.dumps(result, indent=2) + "\n")
    del result["raw_timings"]
    for child in result["fresh_processes"].values():
        child.pop("raw")
    result["full_results"] = str(full_path)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "full_results": str(full_path), "checks": result["checks"], "timings": result["timings"]}, indent=2))


if __name__ == "__main__":
    main()
