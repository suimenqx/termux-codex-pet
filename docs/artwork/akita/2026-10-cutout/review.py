"""Freeze a standalone comparison of the exported experiment and production."""
import argparse
import base64
import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def build(pack: Path, output: Path) -> None:
    def clip(folder):
        manifest=json.loads((folder/'pet.json').read_text())
        return [{'ms':item['duration_ms'], 'png':'data:image/png;base64,'+
                 base64.b64encode((folder/manifest['frames'][item['frame']]['file']).read_bytes()).decode()}
                for item in manifest['clips']['running']['frames']]
    clips=[clip(ROOT/'codex_pet/assets/akita'),clip(pack)]
    output.mkdir(parents=True,exist_ok=True)
    sheet=Image.new('RGB',(768,840),(40,46,54))
    draw=ImageDraw.Draw(sheet)
    for i,item in enumerate(clips[1]):
        path=pack/f'frames/running/{i:02}.png'
        with Image.open(path) as im:
            im=im.convert('RGBa').resize((192,192),Image.Resampling.LANCZOS).convert('RGBA')
            x=i%4*192;y=i//4*210
            sheet.paste(im,(x,y),im)
            draw.text((x+6,y+192),f'{i:02} / {40*i}ms',fill='white')
    sheet.save(output/'contact-sheet.png')
    page='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>秋田犬奔跑：原图拆层实验</title><style>
body{font:16px system-ui;margin:24px;line-height:1.6;background:#ece8df;color:#222}
main{max-width:800px;margin:auto}.pair{display:flex;gap:24px;flex-wrap:wrap}
figure{margin:0;text-align:center}canvas{background:#293039;width:192px;height:192px;border-radius:12px}
button,select{padding:8px;margin:8px 8px 8px 0}input{width:min(90vw,450px)}p{max-width:650px}
</style><main><h1>秋田犬奔跑对照</h1><p>左：当前秋田犬；右：原画拆层实验。两侧均为640ms一圈。
这里只比较持续奔跑；已被用户真机否决：“没有改善，保留原版”。此页仅归档失败实验。浏览器像素不等同手机64dp。</p>
<div class="pair"><figure><canvas id="old" width="256" height="256"></canvas><figcaption>当前原稿</figcaption></figure>
<figure><canvas id="candidate" width="256" height="256"></canvas><figcaption>原画贴图与动作曲线</figcaption></figure></div>
<button id="play">暂停</button><select id="speed"><option value="1">原速</option><option value="0.25">¼速</option></select>
<select id="size"><option value="192">192px</option><option value="64">64px</option><option value="256">256px</option></select>
<button id="bg">切换背景</button><br><input id="time" type="range" min="0" max="639" value="0"><output id="stamp"></output>
<p>检查：头脸是否保持原样，四腿是否各自回收，身体是否配合，循环接缝是否抽动；尤其留意腿根接缝、纸片感和纹理拉伸。</p>
<script>const clips=CLIPS;const canvases=[document.querySelector('#old'),document.querySelector('#candidate')];
let ready=false,playing=true,t=0,last=performance.now(),dark=true;
Promise.all(clips.flat().map(f=>new Promise(r=>{f.image=new Image;f.image.onload=r;f.image.src=f.png}))).then(()=>ready=true);
function frame(list,time){let at=0;for(const f of list){at+=f.ms;if(time<at)return f}return list.at(-1)}
document.querySelector('#play').onclick=()=>{playing=!playing;document.querySelector('#play').textContent=playing?'暂停':'播放'};
document.querySelector('#time').oninput=e=>{t=Number(e.target.value);playing=false;document.querySelector('#play').textContent='播放'};
document.querySelector('#size').onchange=e=>canvases.forEach(c=>c.style.width=c.style.height=e.target.value+'px');
document.querySelector('#bg').onclick=()=>{dark=!dark;canvases.forEach(c=>c.style.background=dark?'#293039':'#fafafa')};
function tick(now){if(playing)t=(t+(now-last)*Number(document.querySelector('#speed').value))%640;last=now;
if(ready)canvases.forEach((c,i)=>{const ctx=c.getContext('2d');ctx.clearRect(0,0,256,256);ctx.drawImage(frame(clips[i],t).image,0,0)});
document.querySelector('#time').value=Math.floor(t);document.querySelector('#stamp').textContent=Math.floor(t)+'ms';requestAnimationFrame(tick)}requestAnimationFrame(tick);
</script></main>'''
    (output/'comparison.html').write_text(page.replace('CLIPS',json.dumps(clips)),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    build(args.pack,args.output)
