#!/usr/bin/env python3
"""Build a browser preview from the Pet's real artwork and frame schedule."""

from __future__ import annotations

import argparse
import base64
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_pet.animation import AKITA_STATES, playback_frames  # noqa: E402
from codex_pet.art import AKITA_SIZE, _decode_rgba_png, icon  # noqa: E402

PET_SIZE_DP = 64
PREVIEW_DENSITY = 3


def _timeline(state: str, cycles: int) -> list[dict[str, object]]:
    result = []
    for scheduled in playback_frames("akita", state, cycles):
        png = icon(state, scheduled.frame, appearance="akita")
        result.append({
            "frame": scheduled.frame,
            "seconds": scheduled.duration_seconds,
            "src": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        })
    return result


def _candidate_timeline(manifest: Path, cycles: int = 1) -> list[dict[str, object]]:
    """Read explicit candidate exposures without replacing production assets."""
    if cycles < 1:
        raise ValueError("cycles must be at least 1")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    exposures = data.get("frames") if isinstance(data, dict) else None
    if not isinstance(exposures, list) or not exposures:
        raise ValueError("candidate manifest needs a nonempty frames list")
    result = []
    for index, exposure in enumerate(exposures):
        if not isinstance(exposure, dict):
            raise ValueError("each candidate exposure must be an object")
        seconds = exposure.get("seconds")
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or seconds <= 0):
            raise ValueError("candidate seconds must be finite and positive")
        filename = exposure.get("file")
        if not isinstance(filename, str) or not filename:
            raise ValueError("candidate exposure needs a file path")
        png = (manifest.parent / filename).read_bytes()
        width, height, _ = _decode_rgba_png(png)
        if (width, height) != (AKITA_SIZE, AKITA_SIZE) or png[24:26] != b"\x08\x06":
            raise ValueError("candidate must be a 256 x 256, 8-bit RGBA PNG")
        result.append({
            "frame": index,
            "seconds": seconds,
            "src": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        })
    return result * cycles


def _html(state: str, cycles: int,
          candidate: list[dict[str, object]] | None = None) -> str:
    timeline = _timeline(state, cycles) if candidate is None else candidate
    if not timeline:
        raise ValueError("preview needs at least one frame")
    frames = json.dumps(timeline, separators=(",", ":"))
    label = state.replace("_", " ").title()
    source = "应用中的生产帧和播放时长" if candidate is None else "候选清单中的帧和播放时长（未替换生产素材）"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Codex Pet 动画预览 · {label}</title>
<style>
  :root {{ color-scheme: dark; font: 15px/1.45 system-ui, sans-serif; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; min-height: 100vh; background: #15191f; color: #eef2f7;
         display: grid; place-items: center; }}
  main {{ width: min(900px, calc(100vw - 32px)); padding: 24px; }}
  h1 {{ margin: 0; font-size: 22px; }}
  .sub {{ margin: 5px 0 20px; color: #abb6c4; }}
  .layout {{ display: grid; grid-template-columns: minmax(250px, 1fr) minmax(260px, 1fr);
             gap: 20px; align-items: stretch; }}
  .stage, .panel {{ border: 1px solid #343c47; border-radius: 14px; background: #1d232b; }}
  .stage {{ min-height: 330px; display: grid; place-items: center; position: relative;
            overflow: hidden; }}
  .pet-frame {{ width: {PET_SIZE_DP * PREVIEW_DENSITY}px; height: {PET_SIZE_DP * PREVIEW_DENSITY}px;
                display: grid; place-items: center; border-radius: 12px;
                background-color: #222831;
                background-image: linear-gradient(45deg, #2d3540 25%, transparent 25%),
                                  linear-gradient(-45deg, #2d3540 25%, transparent 25%),
                                  linear-gradient(45deg, transparent 75%, #2d3540 75%),
                                  linear-gradient(-45deg, transparent 75%, #2d3540 75%);
                background-size: 20px 20px; background-position: 0 0, 0 10px, 10px -10px, -10px 0; }}
  #pet {{ width: 100%; height: 100%; object-fit: contain; }}
  .size {{ position: absolute; bottom: 12px; color: #9eabba; font-size: 12px; }}
  .panel {{ padding: 18px; }}
  .readout {{ display: flex; justify-content: space-between; gap: 12px; color: #abb6c4; }}
  .readout strong {{ color: #fff; }}
  #seek {{ width: 100%; margin: 20px 0 12px; accent-color: #ef8d52; }}
  .buttons {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  button, select {{ border: 1px solid #424d5b; border-radius: 8px; padding: 8px 12px;
                    background: #252d37; color: #f5f7fa; font: inherit; }}
  button {{ cursor: pointer; }} button:hover {{ background: #303a47; }}
  .legend {{ margin-top: 18px; color: #aab5c3; font-size: 13px; }}
  .legend span {{ color: #f5ba8f; }}
  @media (max-width: 620px) {{ .layout {{ grid-template-columns: 1fr; }} .stage {{ min-height: 290px; }} }}
</style>
</head>
<body>
<main>
  <h1>{label} 动画预览</h1>
  <p class="sub">使用{source}；{PET_SIZE_DP * PREVIEW_DENSITY} CSS px 放大预览，实际 {PET_SIZE_DP} dp 效果以设备为准。</p>
  <div class="layout">
    <section class="stage" aria-label="宠物动画画布">
      <div class="pet-frame"><img id="pet" alt="{label} 宠物帧"></div>
      <div class="size">256 × 256 PNG → {PET_SIZE_DP} dp overlay</div>
    </section>
    <section class="panel">
      <div class="readout"><span>循环状态</span><strong id="frame-label"></strong></div>
      <input id="seek" type="range" min="0" max="{len(timeline) - 1}" value="0" aria-label="选择动画帧">
      <div class="buttons">
        <button id="restart">重播</button>
        <button id="pause">暂停</button>
        <button id="previous">上一帧</button>
        <button id="next">下一帧</button>
        <select id="speed" aria-label="播放速度">
          <option value="1">原速</option><option value="0.75">慢速 0.75×</option>
          <option value="0.5">慢速 0.5×</option>
        </select>
      </div>
      <p class="legend">拖动进度条逐帧看姿势。<span>原速</span>对应本次帧清单的曝光时长。</p>
    </section>
  </div>
</main>
<script>
const frames = {frames};
let index = 0;
let playing = true;
let speed = 1;
let timer = null;
const pet = document.getElementById('pet');
const label = document.getElementById('frame-label');
const seek = document.getElementById('seek');
function show(next) {{
  index = (next + frames.length) % frames.length;
  const frame = frames[index];
  pet.src = frame.src;
  label.textContent = `frame ${{String(frame.frame).padStart(2, '0')}} · ${{frame.seconds.toFixed(2)}} s`;
  seek.value = index;
  window.previewFrame = index;
}}
function schedule() {{
  clearTimeout(timer);
  if (!playing) return;
  timer = setTimeout(() => {{ show(index + 1); schedule(); }}, frames[index].seconds * 1000 / speed);
}}
function resume() {{ playing = true; document.getElementById('pause').textContent = '暂停'; schedule(); }}
show(0); schedule();
document.getElementById('pause').addEventListener('click', () => {{
  playing = !playing;
  document.getElementById('pause').textContent = playing ? '暂停' : '继续';
  schedule();
}});
document.getElementById('restart').addEventListener('click', () => {{ show(0); resume(); }});
document.getElementById('previous').addEventListener('click', () => {{ show(index - 1); schedule(); }});
document.getElementById('next').addEventListener('click', () => {{ show(index + 1); schedule(); }});
seek.addEventListener('input', () => {{ show(Number(seek.value)); schedule(); }});
document.getElementById('speed').addEventListener('change', event => {{ speed = Number(event.target.value); schedule(); }});
window.preview = {{ frames, show, pause: () => {{ playing = false; clearTimeout(timer); }} }};
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=AKITA_STATES, default="ready")
    parser.add_argument("--cycles", type=int, default=2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate", type=Path,
                        help="JSON frames list: file (relative to manifest), seconds")
    args = parser.parse_args()
    if args.cycles < 1:
        parser.error("--cycles must be at least 1")

    output = args.output or Path.home() / ".cache" / "codex-pet" / f"preview-{args.state}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    candidate = (_candidate_timeline(args.candidate, args.cycles)
                 if args.candidate is not None else None)
    output.write_text(_html(args.state, args.cycles, candidate), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
