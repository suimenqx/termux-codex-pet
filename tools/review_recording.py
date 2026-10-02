#!/usr/bin/env python3
"""Prepare timestamp-faithful, local recording evidence without editing the input."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from codex_pet.art import _decode_rgba_png, _png


def media_environment(environ=None):
    """Keep Termux media tools out of Codex's bundled, incompatible C++ libs."""
    env = dict(os.environ if environ is None else environ)
    prefix = Path(env.get("PREFIX", "/data/data/com.termux/files/usr"))
    if (prefix / "lib/libc++_shared.so").is_file():
        env["LD_LIBRARY_PATH"] = str(prefix / "lib")
        env.pop("LD_PRELOAD", None)
    return env


def run_media(program, arguments, env):
    executable = shutil.which(program, path=env.get("PATH"))
    if executable is None:
        raise ValueError(f"{program} is required; install ffmpeg before reviewing recordings")
    result = subprocess.run([executable, *map(str, arguments)], env=env,
                            capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise ValueError(f"{program} failed: {result.stderr[-2000:]}")
    return result.stdout


def frame_table(probe):
    stream = next((s for s in probe["streams"] if s.get("codec_type") == "video"), None)
    if stream is None:
        raise ValueError("recording has no video stream")
    frames = probe.get("frames", [])
    if not frames:
        raise ValueError("recording has no decoded video frames")
    timestamps = [float(f["best_effort_timestamp_time"]) for f in frames]
    if not all(math.isfinite(t) for t in timestamps):
        raise ValueError("non-finite video timestamp")
    if any(b < a for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError("video timestamps are out of order; refusing to reorder frames")
    start = timestamps[0]
    end = float(stream.get("start_time", start)) + float(stream.get("duration", 0))
    final_duration = float(frames[-1].get("duration_time",
                           frames[-1].get("pkt_duration_time", max(0, end - timestamps[-1]))))
    if not math.isfinite(final_duration) or final_duration < 0:
        raise ValueError("invalid final video frame duration")
    rows = []
    for index, timestamp in enumerate(timestamps):
        duration = timestamps[index + 1] - timestamp if index + 1 < len(frames) else final_duration
        rows.append({"frame": index, "source_pts_seconds": timestamp,
                     "seconds": timestamp - start, "duration_seconds": duration})
    return stream, rows


def crop_box(value):
    try:
        values = tuple(int(v) for v in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("crop must be x,y,width,height in pixels") from exc
    if len(values) != 4 or min(values[:2]) < 0 or min(values[2:]) <= 0:
        raise argparse.ArgumentTypeError("crop must be nonnegative x,y and positive width,height")
    return values


def window_spec(value):
    try:
        name, begin, end = value.split(":")
        begin, end = float(begin), float(end)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("window must be name:start:end (seconds)") from exc
    if (not re.fullmatch(r"[a-zA-Z0-9_-]+", name) or name.lower() in {"index", "review"}
            or not math.isfinite(begin + end) or not 0 <= begin < end):
        raise argparse.ArgumentTypeError("window needs a safe name and finite 0 <= start < end")
    return name, begin, end


def review_html(rows, title):
    data = json.dumps(rows, ensure_ascii=True).replace("<", "\\u003c")
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>录屏逐帧复核</title><style>
body{font:16px/1.6 system-ui;background:#15191e;color:#eef1f4;margin:24px;max-width:1000px}
button,select{font:inherit;margin:4px;padding:6px}img{image-rendering:auto;max-width:100%}
#stage{min-height:260px;display:flex;align-items:center;justify-content:center;background:#080a0c}
#scrub{width:100%}a{color:#9bd5ff}.grid{display:flex;flex-wrap:wrap;gap:12px}
figure{margin:0;max-width:296px}figcaption{font-size:13px}button:focus-visible{outline:3px solid orange}
</style><h1>__TITLE__</h1><p>原录屏时间戳；不补帧、不改速。空隙代表录屏采样间隔，不能直接判为应用卡顿。</p>
<div id="stage"><img id="frame" alt="宠物录屏帧"></div><output id="label"></output><br>
<button id="prev">上一帧</button><button id="play">播放</button><button id="next">下一帧</button>
<label>速度<select id="speed"><option value="1">原速</option><option value="0.5">半速</option><option value="0.25">四分之一速</option></select></label>
<label>显示<select id="zoom"><option value="1">录屏原像素</option><option value="2">2 倍</option><option value="3">3 倍</option></select></label>
<input id="scrub" aria-label="逐帧定位" type="range" min="0" max="__MAX__" value="0">
<p><a href="manifest.json">处理记录与时间表</a> · <a href="index.html">总览</a></p>
<script>const frames=__DATA__,el=id=>document.getElementById(id);
let index=0,playing=false,origin=0,wall=0,images=[];
function resize(){el('frame').style.width=(el('frame').naturalWidth*Number(el('zoom').value))+'px';}
el('frame').onload=resize;
function paint(){const f=frames[index];el('frame').src=f.file;el('scrub').value=index;resize();
el('label').textContent=`源帧 ${f.frame} · ${f.seconds.toFixed(6)} s · 间隔 ${(f.duration_seconds*1000).toFixed(2)} ms`;
}
function pause(){playing=false;el('play').textContent='播放';}
function seek(i){pause();index=Math.max(0,Math.min(frames.length-1,i));paint();}
el('prev').onclick=()=>seek(index-1);el('next').onclick=()=>seek(index+1);
el('scrub').oninput=e=>seek(Number(e.target.value));el('zoom').onchange=paint;
el('speed').onchange=()=>{origin=frames[index].seconds;wall=performance.now();};
el('play').onclick=()=>{if(playing){pause();return;}if(index===frames.length-1)index=0;
paint();origin=frames[index].seconds;wall=performance.now();playing=true;el('play').textContent='暂停';};
function tick(now){if(playing){let t=origin+(now-wall)/1000*Number(el('speed').value),before=index;
while(index+1<frames.length&&frames[index+1].seconds<=t){index++;}
if(index!==before)paint();
if(t>=frames.at(-1).seconds+frames.at(-1).duration_seconds)pause();}requestAnimationFrame(tick);}
el('play').disabled=true;el('play').textContent='加载中';
Promise.all(frames.map(f=>{const img=new Image();images.push(img);img.src=f.file;return img.decode();}))
.then(()=>{el('play').disabled=false;el('play').textContent='播放';})
.catch(()=>{el('play').disabled=true;el('play').textContent='图片加载失败，请重新打开';});
paint();requestAnimationFrame(tick);</script>'''.replace("__TITLE__", html.escape(title)).replace(
        "__MAX__", str(len(rows) - 1)).replace("__DATA__", data)


# Numeric contact labels: source frame / source-relative milliseconds.
_DIGITS = ("111101101101111", "010110010010111", "111001111100111",
           "111001111001111", "101101111001001", "111100111001111",
           "111100111101111", "111001001001001", "111101111101111", "111101111001111")


def contact_sheet(rows, directory):
    decoded = [_decode_rgba_png((directory / r["file"]).read_bytes()) for r in rows]
    w, h = decoded[0][:2]
    if any(d[:2] != (w, h) for d in decoded):
        raise ValueError("contact sheet images have inconsistent dimensions")
    columns = min(6, len(rows))
    labels = [f'{r["frame"]}/{round(r["seconds"] * 1000)}' for r in rows]
    cell_w, cell_h = max(w, max(map(len, labels)) * 8), h + 18
    width, height = columns * cell_w, math.ceil(len(rows) / columns) * cell_h
    canvas = bytearray(bytes((22, 26, 32, 255)) * width * height)
    for n, (row, (_, _, pixels)) in enumerate(zip(rows, decoded)):
        x, y = n % columns * cell_w, n // columns * cell_h
        for line in range(h):
            offset = ((y + line) * width + x) * 4
            canvas[offset:offset + w * 4] = pixels[line * w * 4:(line + 1) * w * 4]
        label = labels[n]
        for k, char in enumerate(label):
            glyph = "001001010100100" if char == "/" else _DIGITS[int(char)]
            for bit, on in enumerate(glyph):
                if on == "1":
                    for dy in range(2):
                        start = ((y + h + 3 + bit // 3 * 2 + dy) * width + x + k * 8 + bit % 3 * 2) * 4
                        canvas[start:start + 8] = bytes((240, 244, 249, 255)) * 2
    return _png(width, height, canvas)


def prepare(source, output, crop=None, windows=()):
    source, output = source.resolve(), output.resolve()
    if not source.is_file():
        raise ValueError("input video does not exist")
    if output.exists():
        raise ValueError("output already exists; choose a new review directory")
    if windows and crop is None:
        raise ValueError("windows require --crop; run an overview first to choose the region")
    if len({w[0] for w in windows}) != len(windows):
        raise ValueError("window names must be unique")
    for name, start, end in windows:
        window_spec(f"{name}:{start}:{end}")
    env = media_environment()
    probe = json.loads(run_media("ffprobe", ["-v", "error", "-select_streams", "v:0",
        "-show_streams", "-show_format", "-show_frames", "-show_entries",
        "stream=index,codec_type,codec_name,width,height,start_time,duration,avg_frame_rate:stream_side_data=rotation:format=duration,size:frame=best_effort_timestamp_time,duration_time,pkt_duration_time",
        "-of", "json", source], env))
    stream, rows = frame_table(probe)
    width, height = stream["width"], stream["height"]
    if crop and (crop[0] + crop[2] > width or crop[1] + crop[3] > height):
        raise ValueError(f"crop is outside the coded {width}x{height} video")
    duration = rows[-1]["seconds"] + rows[-1]["duration_seconds"]
    selected_windows = []
    for name, start, end in windows:
        selected = [r for r in rows if start <= r["seconds"] < end]
        if end > duration + .001 or not selected:
            raise ValueError(f"window {name} is empty or beyond the video duration")
        selected_windows.append((name, start, end, selected))
    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as video:
        digest = hashlib.file_digest(video, "sha256").hexdigest()
    with tempfile.TemporaryDirectory(prefix=".recording-review-", dir=output.parent) as temp:
        directory = Path(temp) / "review"
        directory.mkdir()
        common = ["-hide_banner", "-loglevel", "error", "-noautorotate", "-i", source,
                  "-map", "0:v:0", "-an"]
        times = [r["seconds"] for r in rows]
        indices = sorted({max(0, bisect_right(times, times[-1] * n / 11) - 1) for n in range(12)})
        (directory / "overview").mkdir()
        selection = "+".join(f"eq(n\\,{n})" for n in indices)
        run_media("ffmpeg", [*common, "-vf", f"select='{selection}',scale=296:-1",
            "-fps_mode", "passthrough", "-start_number", "0", directory / "overview/%06d.png"], env)
        if len(list((directory / "overview").glob("*.png"))) != len(indices):
            raise ValueError("overview frame count differs from selected timestamps")
        overview = [{**rows[i], "file": f"overview/{n:06}.png"} for n, i in enumerate(indices)]
        if crop:
            (directory / "frames").mkdir()
            x, y, w, h = crop
            run_media("ffmpeg", [*common, "-vf", f"crop={w}:{h}:{x}:{y}:exact=1",
                "-fps_mode", "passthrough", "-start_number", "0", directory / "frames/%06d.png"], env)
            if len(list((directory / "frames").glob("*.png"))) != len(rows):
                raise ValueError("decoded frame count differs from timestamps; refusing misaligned evidence")
            for row in rows:
                row["file"] = f'frames/{row["frame"]:06}.png'
            (directory / "review.html").write_text(review_html(rows, source.name), encoding="utf-8")
        reports = []
        for name, start, end, selected in selected_windows:
            pages = []
            for n in range(0, len(selected), 24):
                filename = f"{name}-{n // 24 + 1:03}.png"
                (directory / filename).write_bytes(contact_sheet(selected[n:n + 24], directory))
                pages.append({"file": filename, "frames": [r["frame"] for r in selected[n:n + 24]]})
            (directory / f"{name}.html").write_text(review_html(selected, name), encoding="utf-8")
            reports.append({"name": name, "start": start, "end": end, "pages": pages})
        deltas = [r["duration_seconds"] for r in rows[:-1]]
        manifest = {"schema": 1, "source": {"file": source.name, "sha256": digest,
            "bytes": source.stat().st_size}, "stream": stream, "duration_seconds": duration,
            "crop_xywh": crop, "autorotate": False, "audio_extracted": False,
            "frame_count": len(rows), "frames": rows, "overview": overview, "windows": reports,
            "intervals": {"median_seconds": statistics.median(deltas) if deltas else None,
                          "max_seconds": max(deltas, default=0)},
            "interpretation": "Intervals are recording samples, not proof of app frame drops.",
            "tools": {tool: run_media(tool, ["-version"], env).splitlines()[0] for tool in ("ffmpeg", "ffprobe")}}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        cards = "".join(f'<figure><img src="{r["file"]}" alt="录屏缩略图"><figcaption>源帧 {r["frame"]} · {r["seconds"]:.6f} s</figcaption></figure>' for r in overview)
        links = ('<a href="review.html">完整宠物片段</a> · ' if crop else "") + " · ".join(
            f'<a href="{r["name"]}.html">{r["name"]}</a>' for r in reports)
        (directory / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>录屏复核</title>'
            '<style>body{font:16px system-ui;background:#171c22;color:white}a{color:#a9d8ff}.grid{display:flex;flex-wrap:wrap}figure{margin:8px}</style>'
            f'<h1>{html.escape(source.name)}</h1><p>{len(rows)} 帧 · {duration:.3f} 秒 · 编码尺寸 {width}×{height}。裁剪坐标采用编码方向，不自动旋转。</p>'
            f'<p>{links}</p><p><a href="manifest.json">处理记录</a></p><div class="grid">{cards}</div>', encoding="utf-8")
        if output.exists():
            raise ValueError("output was created by another process; refusing to overwrite it")
        directory.rename(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--crop", type=crop_box, help="x,y,width,height in coded video pixels")
    parser.add_argument("--window", action="append", type=window_spec, default=[], help="name:start:end in recording seconds; repeatable")
    args = parser.parse_args()
    output = args.output or Path.home() / ".cache/codex-pet/recordings" / (
        args.video.stem + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    try:
        result = prepare(args.video, output, args.crop, args.window)
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Recording review failed: {exc}\n")
    print(f'{result["frame_count"]} original frames; {result["duration_seconds"]:.3f}s; {output.resolve() / "index.html"}')


if __name__ == "__main__":
    main()
