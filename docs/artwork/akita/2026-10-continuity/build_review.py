from pathlib import Path
import json,base64,sys
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.historical_animation import playback_frames,akita_artwork_frame
from tools.historical_art import icon
p = Path(__file__).resolve().parent
def frame(data,seconds,label):return {'src':'data:image/png;base64,'+base64.b64encode(data).decode(),'seconds':seconds,'label':label}
def current(state,source=None):return [frame(icon(state,s.frame),s.duration_seconds,str(akita_artwork_frame(state,s.frame))) for s in playback_frames('akita',state,from_state=source)]
oldrun=[frame((p/f'originals/running/{n:02}.png').read_bytes(),.08,f'running/{n:02}') for n in range(8)]
oldready=[frame((p/f'originals/ready/{n:02}.png').read_bytes(),.12,f'ready/{n:02}') for n in [5,6]]+current('ready')
data={'running':[oldrun,current('running')],'ready':[oldready,current('ready','running')]}
html='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>秋田犬连续性对照</title>
<style>body{font:16px system-ui;max-width:760px;margin:24px auto;background:#182029;color:#eee;padding:12px}section{display:flex;gap:24px;margin-top:24px}.panel{flex:1}img{display:block;width:64px;height:64px;background:repeating-conic-gradient(#35404a 0 25%,#28323b 0 50%) 0/16px 16px}button,select{font:inherit;margin:8px 4px;padding:6px}input{width:100%}code{display:block;font-size:13px;min-height:3em}p{line-height:1.6}</style>
<h1>秋田犬连续性对照</h1><p>左侧为7dc1042，右侧为本轮。默认64 CSS px，便于在同一显示尺寸比较；浏览器不代表Android原生像素或定时精度。奔跑两侧均640ms，原关键图时刻相同；Ready进入分别1.18s和1.30s，新增转体用120ms。设备观感待录屏确认。</p>
<label>动作<select id="motion"><option value="running">奔跑</option><option value="ready">Running → Ready</option></select></label>
<label>尺寸<select id="size"><option>64</option><option>192</option><option>256</option></select></label>
<label>速度<select id="speed"><option value="1">原速</option><option value="0.25">¼速</option></select></label><button id="play">暂停</button><input id="time" type="range" min="0" step="0.001"><output id="clock"></output>
<section><div class="panel"><h2>修改前</h2><img id="before" alt="原动画"><code id="beforeLabel"></code></div><div class="panel"><h2>修改后</h2><img id="after" alt="新动画"><code id="afterLabel"></code></div></section>
<script>const clips=DATA;let playing=true,t=0,previous=performance.now();const ids=['before','after'];const motion=document.querySelector('#motion'),slider=document.querySelector('#time');function duration(a){return a.reduce((s,f)=>s+f.seconds,0)}function draw(){const rows=clips[motion.value];slider.max=Math.max(...rows.map(duration));slider.value=t;document.querySelector('#clock').textContent=t.toFixed(3)+' s';rows.forEach((frames,i)=>{let local=t%duration(frames),f=frames.at(-1);for(const pose of frames){if(local<pose.seconds){f=pose;break}local-=pose.seconds}document.getElementById(ids[i]).src=f.src;document.getElementById(ids[i]+'Label').textContent=f.label+' · '+Math.round(f.seconds*1000)+'ms'})}motion.onchange=()=>{t=0;draw()};slider.oninput=()=>{t=Number(slider.value);playing=false;document.querySelector('#play').textContent='播放';draw()};document.querySelector('#play').onclick=()=>{playing=!playing;document.querySelector('#play').textContent=playing?'暂停':'播放'};document.querySelector('#size').onchange=e=>{for(const id of ids){const im=document.getElementById(id);im.style.width=im.style.height=e.target.value+'px'}};function tick(now){if(playing){t=(t+(now-previous)/1000*Number(document.querySelector('#speed').value))%Math.max(...clips[motion.value].map(duration));draw()}previous=now;requestAnimationFrame(tick)}draw();requestAnimationFrame(tick);</script>'''.replace('DATA',json.dumps(data,separators=(',',':')))
(p/'comparison.html').write_text(html)
from tools.audit_animation import render_audit, write_audit
for state in ['running', 'ready']:
    result = render_audit(state, cycles=2, density=3,
                          from_state='running' if state == 'ready' else None)
    write_audit(result, p / 'review' / state)
