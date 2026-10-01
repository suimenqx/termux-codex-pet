"""Build a self-contained, synchronized artwork review (not the runtime UI)."""
import base64
import json
import runpy
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from tools.prepare_running_frames import split_sheet

def uri(data):
    return 'data:image/png;base64,'+base64.b64encode(data).decode('ascii')

old = [uri(p) for p in split_sheet((ROOT/'docs/artwork/running-gait-sheet.png').read_bytes())]
exporter = runpy.run_path(str(HERE / 'export_candidate.py'))
new = [uri(exporter['export_frame'](i)) for i in range(16)]
ready = uri((ROOT/'codex_pet/assets/akita/frames/ready/00.png').read_bytes())
html = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>秋田犬跑姿对照</title><style>
*{box-sizing:border-box}body{margin:0;background:#14191f;color:#edf2f5;font:16px/1.6 system-ui,sans-serif}
main{max-width:920px;margin:auto;padding:24px}h1{font-size:25px;margin:0 0 6px}p{color:#b8c5d0}
.panels{display:flex;flex-wrap:wrap;gap:20px;margin:24px 0}.panel{flex:1;min-width:230px}
.stage{height:240px;display:flex;align-items:center;justify-content:center;background:repeating-conic-gradient(#27313b 0% 25%,#303b46 0% 50%) 0/20px 20px;border-radius:12px}
img{width:192px;height:192px}.caption{margin-top:8px}small{color:#b8c5d0}
.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:12px 0}button,select{font:inherit;padding:6px 12px;border:1px solid #64798b;background:#223141;color:white;border-radius:8px}input[type=range]{width:100%;accent-color:#ffa75d}button:focus-visible,select:focus-visible,input:focus-visible{outline:3px solid #ffa75d}
</style><main><h1>秋田犬跑姿对照</h1>
<p>同一时间轴、相同画布显示大小。两版均为 640 ms 一轮；新稿为 16 张独立画稿。右侧 Ready 用于对照体量与表情。</p>
<div class="panels"><section class="panel"><div class="stage"><img id="old" alt="原版秋田犬跑步"></div><div class="caption">原版 · d1b63b7 · 8 帧</div></section>
<section class="panel"><div class="stage"><img id="new" alt="新稿秋田犬跑步"></div><div class="caption">新稿 · 16 帧</div></section>
<section class="panel"><div class="stage"><img id="ready" alt="Ready 首帧"></div><div class="caption">Ready · 原图</div></section></div>
<div class="controls"><button id="toggle">暂停</button><label>速度 <select id="speed"><option value="1">原速</option><option value="0.5">半速</option><option value="0.25">四分之一速</option></select></label>
<label>图像大小 <select id="size"><option value="192">192 px</option><option value="64">64 px</option></select></label>
<label>背景 <select id="bg"><option value="checker">棋盘</option><option value="#f4f2ed">浅色</option><option value="#101419">深色</option></select></label></div>
<label for="scrub">逐帧查看（移动滑块暂停）</label><input id="scrub" type="range" min="0" max="639" step="1" value="0"><output id="position"></output>
<p><small>浏览器 CSS 像素不等同于 Android dp。设备是否顺畅、神态是否符合预期仍须看实际悬浮窗；此页不会更改宠物设置。</small></p></main><script>
const OLD=__OLD__,NEW=__NEW__,READY=__READY__;
const el=id=>document.getElementById(id);el('ready').src=READY;
let time=0,last=performance.now(),playing=true,rate=1;
function paint(){const t=((time%640)+640)%640;const a=Math.floor(t/80),b=Math.floor(t/40);if(el('old').src!==OLD[a])el('old').src=OLD[a];if(el('new').src!==NEW[b])el('new').src=NEW[b];el('scrub').value=Math.floor(t);el('position').textContent=`${Math.floor(t)} ms · 原版 ${a} / 新稿 ${b}`;}
el('toggle').onclick=()=>{playing=!playing;el('toggle').textContent=playing?'暂停':'播放';last=performance.now();};
el('speed').onchange=e=>{rate=Number(e.target.value);};
el('scrub').oninput=e=>{playing=false;el('toggle').textContent='播放';time=Number(e.target.value);paint();};
el('size').onchange=e=>document.querySelectorAll('img').forEach(i=>{i.style.width=i.style.height=e.target.value+'px';});
el('bg').onchange=e=>document.querySelectorAll('.stage').forEach(s=>{s.style.background=e.target.value==='checker'?'':e.target.value;});
async function start(){await Promise.all([...OLD,...NEW,READY].map(src=>{const i=new Image();i.src=src;return i.decode();}));paint();last=performance.now();function tick(now){if(playing)time+=(now-last)*rate;last=now;paint();requestAnimationFrame(tick);}requestAnimationFrame(tick);}start().catch(()=>el('position').textContent='图像加载失败，请重新打开。');
</script></html>'''
html = html.replace('__OLD__', json.dumps(old)).replace('__NEW__',json.dumps(new)).replace('__READY__',json.dumps(ready))
(HERE/'comparison.html').write_text(html)
print(HERE/'comparison.html')
