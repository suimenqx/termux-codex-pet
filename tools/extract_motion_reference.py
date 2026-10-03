#!/usr/bin/env python3
"""Extract a clean, timestamped motion reference from a screen recording.

The tool keeps the recording untouched, crops a fixed ROI, merges only
near-identical consecutive capture samples, and removes the dark recording
background into straight-alpha PNG frames.  It never interpolates motion or
changes the production pet pack.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.review_recording import crop_box, frame_table, media_environment, run_media


def _smoothstep(value: np.ndarray, low: float, high: float) -> np.ndarray:
    if not high > low:
        raise ValueError("smoothstep high must be greater than low")
    t = np.clip((value - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def clean_alpha(rgb: np.ndarray) -> np.ndarray:
    """Build a conservative alpha matte for the dark screen background.

    The recording uses a nearly black GUI background.  Luma keeps the white
    muzzle and paws, while saturation retains orange fur and its anti-aliased
    edge.  Pixels below the small cutoff are fully transparent, so compression
    noise in the screen background cannot become a halo in the reference.
    """

    if rgb.ndim != 3 or rgb.shape[-1] != 3:
        raise ValueError("clean_alpha expects an HxWx3 RGB array")
    values = rgb.astype(np.float32)
    luma = values @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    saturation = values.max(axis=2) - values.min(axis=2)
    alpha = np.maximum(
        _smoothstep(luma, 16.0, 34.0),
        0.72 * _smoothstep(saturation, 7.0, 24.0),
    )
    alpha[alpha < 0.06] = 0.0
    return np.rint(alpha * 255.0).clip(0, 255).astype(np.uint8)


def clean_frame(rgb: np.ndarray) -> np.ndarray:
    """Return a straight-alpha RGBA frame with hidden RGB cleared."""

    alpha = clean_alpha(rgb)
    rgba = np.dstack((rgb.astype(np.uint8), alpha))
    rgba[alpha == 0, :3] = 0
    return rgba


def merge_capture_samples(
    frames: list[np.ndarray], threshold: float = 5.0
) -> list[list[int]]:
    """Group consecutive recording samples that show the same app frame.

    A screen recorder can capture one GUI frame more than once.  Grouping is
    deliberately local and conservative: as soon as the mean absolute RGB
    difference exceeds ``threshold``, a new motion sample starts.  The caller
    may median each group to reduce codec noise without inventing an in-between
    pose.
    """

    if threshold < 0:
        raise ValueError("threshold must be nonnegative")
    if not frames:
        return []
    groups: list[list[int]] = [[0]]
    for index in range(1, len(frames)):
        if frames[index].shape != frames[index - 1].shape:
            raise ValueError("capture frames have inconsistent dimensions")
        difference = float(
            np.mean(
                np.abs(
                    frames[index].astype(np.float32)
                    - frames[index - 1].astype(np.float32)
                )
            )
        )
        if difference <= threshold:
            groups[-1].append(index)
        else:
            groups.append([index])
    return groups


def _rgba_png(path: Path, rgba: np.ndarray) -> None:
    Image.fromarray(rgba, "RGBA").save(path, format="PNG", optimize=True)


def _composite(rgba: np.ndarray, background: tuple[int, int, int]) -> np.ndarray:
    base = np.empty(rgba.shape, dtype=np.uint8)
    base[:, :, :3] = np.array(background, dtype=np.uint8)
    base[:, :, 3] = 255
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    base[:, :, :3] = np.rint(
        rgba[:, :, :3].astype(np.float32) * alpha
        + base[:, :, :3].astype(np.float32) * (1.0 - alpha)
    ).clip(0, 255).astype(np.uint8)
    return base[:, :, :3]


def _contact_sheet(entries: list[dict], frames: list[np.ndarray], path: Path) -> None:
    """Write a neutral-background contact sheet with source timing labels."""

    cell_width, cell_height = 240, 224
    columns = min(4, max(1, len(frames)))
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), (38, 42, 48))
    for index, (entry, rgba) in enumerate(zip(entries, frames)):
        rgb = _composite(rgba, (224, 224, 224))
        image = Image.fromarray(rgb, "RGB").resize(
            (cell_width, cell_height - 24), Image.Resampling.NEAREST
        )
        card = Image.new("RGB", (cell_width, cell_height), (224, 224, 224))
        card.paste(image, (0, 0))
        draw = ImageDraw.Draw(card)
        label = (
            f'{index:02d}  {entry["source_pts_seconds"]:.3f}s '
            f'[{entry["source_frame_start"]}:{entry["source_frame_end"]}]'
        )
        draw.rectangle((0, cell_height - 24, cell_width, cell_height), fill=(20, 24, 29))
        draw.text((5, cell_height - 20), label, fill=(245, 247, 249))
        sheet.paste(card, ((index % columns) * cell_width, (index // columns) * cell_height))
    sheet.save(path, format="PNG", optimize=True)


def _write_concat(entries: list[dict], directory: Path) -> Path:
    concat = directory / "video.concat.txt"
    lines: list[str] = []
    for entry in entries:
        relative = f'video_frames/{entry["index"]:04d}.png'
        lines.append(f"file '{relative}'")
        lines.append(f'duration {entry["duration_seconds"]:.9f}')
    # concat requires the final file to appear twice for the final duration to
    # be honored by all supported ffmpeg versions.
    if entries:
        lines.append(f"file 'video_frames/{entries[-1]['index']:04d}.png'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return concat


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _model_brief(manifest: dict) -> str:
    source = manifest["source"]
    interval = manifest["interval"]
    return f"""# 秋田犬跑步动作参考包

这是从最新录屏中提取的动作参考，不是生产素材替换。原录屏保持不变；本包只提供固定 ROI、去除深色录屏背景后的透明帧、带中性背景的视频和时间表。

## 给视频/动画模型的输入

- 角色身份以项目中的秋田犬生产帧为准；不要把录屏背景、黑色边缘或压缩噪声当成角色。
- 使用 `frames/` 的透明帧理解四肢路径，使用 `akita-running-reference-4x.mp4` 理解连续节奏。
- `contact-sheet.png` 显示了去重后的顺序；`manifest.json` 的 `source_pts_seconds` 和 `duration_seconds` 是录屏证据。
- 保持头脸、胸髋体量、蓝色项圈和侧向镜头；补足四肢连接、身体起伏和首尾循环，不能改变角色身份。
- 目标是生成一轮可循环的流畅跑步动作，先输出透明 PNG 帧序列和逐帧时间，再输出视频。不要使用光流把录屏采样误认为真实中间姿势。

## 提取依据

- 原文件：`{source['file']}`
- SHA-256：`{source['sha256']}`
- 编码尺寸：`{source['width']}×{source['height']}`
- ROI（编码像素 x,y,w,h）：`{manifest['crop_xywh']}`
- 跑步窗口：`{interval['start_seconds']:.6f}–{interval['end_seconds']:.6f} s`
- 去重：连续 RGB 平均绝对差 ≤ `{manifest['dedupe']['threshold']}` 的采样合并，中值降噪；未插帧、未改速。

## 接回项目前必须完成

生成模型的结果只能先放在候选目录。按 `docs/animation-assets.md`、`docs/animation-motion.md`、`docs/animation-gait.md` 和 `docs/animation-acceptance.md` 检查固定画布、模型尺度、四肢接触表、循环接缝、透明边缘和真机 PNG 路径；用户看过连续跑步与拖动后，才允许把候选导出到 `codex_pet/assets/akita/frames/running/`。本参考包本身不会改动当前生产帧。

生成视频若要导入，请保留模型实际输出、提示词和哈希，再按同一候选流程抽取透明 PNG；MP4 本身不能证明透明通道或固定画布正确。
"""


def prepare(
    video: Path,
    output: Path,
    crop: tuple[int, int, int, int],
    start: float,
    end: float,
    dedupe_threshold: float = 5.0,
    scale: int = 4,
) -> dict:
    video = video.resolve()
    output = output.resolve()
    if not video.is_file():
        raise ValueError(f"input video does not exist: {video}")
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    if not 0 <= start < end:
        raise ValueError("window must satisfy 0 <= start < end")
    if scale < 1:
        raise ValueError("scale must be positive")

    environment = media_environment()
    probe = json.loads(
        run_media(
            "ffprobe",
            [
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_streams",
                "-show_format",
                "-show_frames",
                "-show_entries",
                "stream=index,codec_type,codec_name,width,height,start_time,duration,avg_frame_rate:stream_side_data=rotation:format=duration,size:frame=best_effort_timestamp_time,duration_time,pkt_duration_time",
                "-of",
                "json",
                video,
            ],
            environment,
        )
    )
    stream, rows = frame_table(probe)
    x, y, width, height = crop
    if x + width > stream["width"] or y + height > stream["height"]:
        raise ValueError("crop is outside the coded video")
    selected = [row for row in rows if start <= row["seconds"] < end]
    if not selected:
        raise ValueError("requested motion window contains no video frames")

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        raw_directory = staging / "decoded"
        raw_directory.mkdir()
        run_media(
            "ffmpeg",
            [
                "-hide_banner",
                "-loglevel",
                "error",
                "-noautorotate",
                "-i",
                video,
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                f"crop={width}:{height}:{x}:{y}:exact=1",
                "-fps_mode",
                "passthrough",
                "-start_number",
                "0",
                raw_directory / "%06d.png",
            ],
            environment,
        )
        raw_paths = sorted(raw_directory.glob("*.png"))
        if len(raw_paths) != len(rows):
            raise ValueError(
                f"decoded frame count {len(raw_paths)} differs from timestamps {len(rows)}"
            )

        selected_images = [
            np.asarray(Image.open(raw_paths[row["frame"]]).convert("RGB"))
            for row in selected
        ]
        groups = merge_capture_samples(selected_images, dedupe_threshold)
        frames_directory = staging / "frames"
        scaled_directory = staging / f"frames_{scale}x"
        video_directory = staging / "video_frames"
        frames_directory.mkdir()
        scaled_directory.mkdir()
        video_directory.mkdir()
        entries: list[dict] = []
        cleaned_frames: list[np.ndarray] = []
        clip_end = min(end, rows[-1]["seconds"] + rows[-1]["duration_seconds"])
        for index, group in enumerate(groups):
            stack = np.stack([selected_images[position] for position in group], axis=0)
            rgba = clean_frame(np.rint(np.median(stack, axis=0)).astype(np.uint8))
            cleaned_frames.append(rgba)
            first = selected[group[0]]
            next_start = (
                selected[groups[index + 1][0]]["seconds"]
                if index + 1 < len(groups)
                else clip_end
            )
            duration = next_start - first["seconds"]
            if duration <= 0:
                raise ValueError("non-positive extracted frame duration")
            entry = {
                "index": index,
                "source_frame_start": selected[group[0]]["frame"],
                "source_frame_end": selected[group[-1]]["frame"],
                "source_pts_seconds": first["source_pts_seconds"],
                "seconds": first["seconds"],
                "duration_seconds": duration,
                "capture_samples": len(group),
            }
            entries.append(entry)
            _rgba_png(frames_directory / f"{index:04d}.png", rgba)
            scaled = Image.fromarray(rgba, "RGBA").resize(
                (width * scale, height * scale), Image.Resampling.LANCZOS
            )
            scaled.save(scaled_directory / f"{index:04d}.png", format="PNG", optimize=True)
            rgb = _composite(np.asarray(scaled), (224, 224, 224))
            Image.fromarray(rgb, "RGB").save(
                video_directory / f"{index:04d}.png", format="PNG", optimize=True
            )

        tool_versions = {
            tool: run_media(tool, ["-version"], environment).splitlines()[0]
            for tool in ("ffmpeg", "ffprobe")
        }
        manifest = {
            "schema": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "source": {
                "file": video.name,
                "path": str(video),
                "sha256": _sha256(video),
                "bytes": video.stat().st_size,
                "width": stream["width"],
                "height": stream["height"],
                "codec": stream.get("codec_name"),
                "frame_count": len(rows),
                "duration_seconds": rows[-1]["seconds"] + rows[-1]["duration_seconds"],
            },
            "crop_xywh": list(crop),
            "interval": {
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": clip_end - start,
            },
            "dedupe": {
                "threshold": dedupe_threshold,
                "method": "consecutive RGB mean absolute difference; median per group",
                "input_frames": len(selected),
                "output_frames": len(entries),
            },
            "frames": entries,
            "tools": tool_versions,
            "outputs": {
                "transparent_native": "frames/",
                "transparent_scaled": f"frames_{scale}x/",
                "video": f"akita-running-reference-{scale}x.mp4",
                "contact_sheet": "contact-sheet.png",
            },
            "limitations": [
                "This is screen-recording evidence; it is not a motion-capture ground truth.",
                "No optical-flow interpolation or AI-generated intermediate frame was used.",
                "The transparent matte removes the dark recording background by color/luma; inspect edges before production use.",
            ],
        }
        concat = _write_concat(entries, staging)
        video_output = staging / f"akita-running-reference-{scale}x.mp4"
        run_media(
            "ffmpeg",
            [
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "12",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-fps_mode",
                "vfr",
                "-video_track_timescale",
                "1000000",
                "-t",
                f"{clip_end - start:.9f}",
                video_output,
            ],
            environment,
        )
        if not video_output.is_file() or video_output.stat().st_size == 0:
            raise ValueError("ffmpeg did not create the cleaned reference video")
        encoded_probe = json.loads(
            run_media(
                "ffprobe",
                [
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    video_output,
                ],
                environment,
            )
        )
        encoded_stream = encoded_probe.get("streams", [{}])[0]
        encoded_frames = int(encoded_stream.get("nb_frames", len(entries)))
        encoded_duration = float(encoded_probe.get("format", {}).get("duration", 0))
        if encoded_frames < len(entries) or encoded_duration <= 0:
            raise ValueError("encoded reference video failed its frame/timing check")
        manifest["outputs"]["video_sha256"] = _sha256(video_output)
        manifest["outputs"]["video_probe"] = {
            "codec": encoded_stream.get("codec_name"),
            "width": encoded_stream.get("width"),
            "height": encoded_stream.get("height"),
            "frame_count": encoded_frames,
            "duration_seconds": encoded_duration,
            "audio": False,
        }
        _contact_sheet(entries, cleaned_frames, staging / "contact-sheet.png")
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (staging / "README.md").write_text(_model_brief(manifest), encoding="utf-8")
        shutil.rmtree(raw_directory)
        shutil.rmtree(video_directory)
        concat.unlink()
        staging.rename(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--crop", type=crop_box, required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--dedupe-threshold", type=float, default=5.0)
    parser.add_argument("--scale", type=int, default=4)
    args = parser.parse_args()
    try:
        manifest = prepare(
            args.video,
            args.output,
            args.crop,
            args.start,
            args.end,
            args.dedupe_threshold,
            args.scale,
        )
    except (ValueError, OSError, KeyError, RuntimeError) as error:
        parser.exit(1, f"Motion reference extraction failed: {error}\n")
    print(
        f"{manifest['dedupe']['output_frames']} cleaned frames; "
        f"{manifest['interval']['duration_seconds']:.3f}s; "
        f"{args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
