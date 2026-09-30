#!/usr/bin/env python3
"""Build a browser preview from the Pet's real artwork and frame schedule."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codex_pet.art import (  # noqa: E402
    AKITA_FRAME_COUNTS,
    AKITA_LOOP_STATES,
    AKITA_READY_LOOP_START,
    AKITA_STATES,
    advance_animation,
    animation_interval,
    icon,
)

PET_SIZE_DP = 64
PREVIEW_DENSITY = 3
FINAL_HOLD_SECONDS = 0.8


def _timeline(state: str, cycles: int) -> list[dict[str, object]]:
    frame_count = AKITA_FRAME_COUNTS[state]
    if state == "ready":
        step_count = frame_count + (cycles - 1) * (frame_count - AKITA_READY_LOOP_START)
    elif state in AKITA_LOOP_STATES:
        step_count = frame_count * cycles
    else:
        step_count = frame_count + 1

    result = []
    frame = 0
    for _ in range(step_count):
        interval = animation_interval("akita", state, frame)
        if interval is None:
            interval = FINAL_HOLD_SECONDS
        png = icon(state, frame, appearance="akita")
        result.append({
            "frame": frame,
            "seconds": interval,
            "src": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        })
        next_frame = advance_animation("akita", state, frame)
        if next_frame == frame and interval == FINAL_HOLD_SECONDS:
            break
        frame = next_frame
    return result


def _html(state: str, cycles: int) -> str:
    frames = json.dumps(_timeline(state, cycles), separators=(",", ":"))
    label = state.replace("_", " ").title()
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
  <p class="sub">使用应用中的秋田犬 PNG 帧、状态顺序和播放时长；宠物显示尺寸为 {PET_SIZE_DP} dp（按 {PREVIEW_DENSITY}×密度预览）。</p>
  <div class="layout">
    <section class="stage" aria-label="宠物动画画布">
      <div class="pet-frame"><img id="pet" alt="{label} 宠物帧"></div>
      <div class="size">256 × 256 PNG → {PET_SIZE_DP} dp overlay</div>
    </section>
    <section class="panel">
      <div class="readout"><span>循环状态</span><strong id="frame-label"></strong></div>
      <input id="seek" type="range" min="0" max="{len(_timeline(state, cycles)) - 1}" value="0" aria-label="选择动画帧">
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
      <p class="legend">拖动进度条逐帧看姿势。<span>原速</span>对应应用中的真实帧间隔。</p>
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
    args = parser.parse_args()
    if args.cycles < 1:
        parser.error("--cycles must be at least 1")

    output = args.output or Path.home() / ".cache" / "codex-pet" / f"preview-{args.state}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_html(args.state, args.cycles), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
