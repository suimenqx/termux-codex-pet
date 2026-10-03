"""Offline cutout experiment: original pixels, continuous gait, separate pet ID."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
SIZE = 256
PET_ID = 'akita_run_cutout_v1'
PERIOD_MS = 640
FRAME_MS = 40
POLYGONS = {
    'tail': [(25,70),(103,62),(113,87),(108,113),(83,141),(25,133)],
    'body': [(29,136),(87,111),(129,114),(175,138),(198,156),(198,174),
             (192,184),(181,191),(165,195),(144,192),(120,189),(97,182),
             (80,187),(62,195),(49,193),(39,186),(34,172)],
    'hind': [(30,147),(48,132),(79,132),(95,146),(97,170),(88,190),
             (86,203),(101,210),(98,225),(78,231),(53,221),(45,204),(39,189)],
    'fore': [(112,148),(137,142),(151,162),(161,183),(166,205),
             (192,216),(194,239),(166,242),(146,229),(133,207),(114,182)],
    'head': [(119,40),(253,40),(254,145),(231,150),(216,153),(201,156),
             (193,163),(177,165),(160,161),(143,155),(124,146),(111,133),
             (109,118),(115,93)],
}
ANCHORS = {
    'fore': np.array([[133.,159.],[147.,188.],[172.,224.]]),
    'hind': np.array([[66.,158.],[78.,187.],[79.,214.]]),
}
LEGS = (
    ('far_hind','hind',0.00,88.,166.,211.,0.88,0.80),
    ('far_fore','fore',0.38,156.,163.,220.,0.90,0.84),
    ('near_hind','hind',0.12,66.,158.,224.,1.0,1.0),
    ('near_fore','fore',0.50,133.,159.,233.,1.0,1.0),
)


def cut(source: Image.Image, name: str) -> Image.Image:
    mask = Image.new('L',(SIZE,SIZE))
    ImageDraw.Draw(mask).polygon(POLYGONS[name], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.65))
    rgba = np.array(source)
    if name=='body':
        # The original arm occludes the belly. Reconstruct only this hidden
        # patch from original cream chest pixels, never the face or collar.
        patch=source.crop((166,166,190,183)).convert('RGBa')
        patch=patch.resize((91,39),Image.Resampling.BICUBIC).convert('RGBA')
        plate=source.copy();plate.alpha_composite(patch,(103,160))
        blend=Image.new('L',(SIZE,SIZE))
        ImageDraw.Draw(blend).polygon([(108,181),(130,176),(151,168),(173,165),
                                      (193,166),(199,195),(108,199)],fill=255)
        blend=blend.filter(ImageFilter.GaussianBlur(3))
        rgba=np.array(Image.composite(plate,source,blend))
    rgba[:,:,3] = (rgba[:,:,3].astype(np.uint16)*np.array(mask)//255).astype(np.uint8)
    rgba[rgba[:,:,3]==0,:3] = 0
    return Image.fromarray(rgba)


def body_dy(x: np.ndarray | float, phase: float) -> np.ndarray:
    blend = np.clip((np.asarray(x)-66)/90,0,1)
    hip = 3.5*math.cos(2*math.pi*(phase-.14))
    chest = 3.0*math.cos(2*math.pi*(phase-.54))
    return hip*(1-blend)+chest*blend


def foot(phase: float, onset: float, root_x: float, ground: float) -> tuple[np.ndarray,bool]:
    p=(phase-onset)%1.0
    stance=.28
    if p < stance:
        return np.array([root_x+28-52*p/stance,ground-8]),True
    u=(p-stance)/(1-stance)
    tangent=-52/stance*(1-stance)
    x=(2*u**3-3*u**2+1)*(-24)+(u**3-2*u**2+u)*tangent
    x+=(-2*u**3+3*u**2)*28+(u**3-u**2)*tangent
    return np.array([root_x+x,ground-8-27*math.sin(math.pi*u)**2]),False


def joints(kind: str, origin: np.ndarray, paw: np.ndarray, scale: float) -> np.ndarray:
    # Knee bends forward; elbow bends backward. Reach is recorded separately.
    lengths=(33*scale,35*scale) if kind=='fore' else (32*scale,32*scale)
    vector=paw-origin
    distance=float(np.linalg.norm(vector))
    direction=vector/max(distance,1e-8)
    a=(lengths[0]**2-lengths[1]**2+distance**2)/(2*max(distance,1e-8))
    h=math.sqrt(max(0.,lengths[0]**2-a*a))
    normal=np.array([-direction[1],direction[0]])
    knee=origin+a*direction+normal*h*(1 if kind=='fore' else -1)
    return np.array([origin,knee,paw])


def skin(points: np.ndarray, source: np.ndarray, target: np.ndarray, scale: float) -> np.ndarray:
    segment=source[2]-source[0]
    length=np.linalg.norm(segment)
    direction=segment/length
    u=(points-source[0])@direction/length
    v=(points-source[0])@np.array([-direction[1],direction[0]])
    t=u[:,None]
    middle=(target[0]+target[2])/2
    control=middle+1.2*(target[1]-middle)
    center=(1-t)**2*target[0]+2*t*(1-t)*control+t*t*target[2]
    tangent=2*(1-t)*(control-target[0])+2*t*(target[2]-control)
    tangent/=np.maximum(np.linalg.norm(tangent,axis=1)[:,None],1e-8)
    normal=np.stack((-tangent[:,1],tangent[:,0]),axis=1)
    result=center+v[:,None]*normal*scale
    attachment=np.clip((u-.08)/.42,0,1)
    attachment=attachment*attachment*(3-2*attachment)
    fixed_root=target[0]+(points-source[0])*scale
    result=fixed_root*(1-attachment[:,None])+result*attachment[:,None]
    # Preserve the original paw drawing's orientation near the toe.
    paw=np.clip((u-.76)/.30,0,1)
    paw=paw*paw*(3-2*paw)
    fixed=target[2]+(points-source[2])*scale
    return result*(1-paw[:,None])+fixed*paw[:,None]


def warp(layer: Image.Image, deform) -> Image.Image:
    """Forward a small regular triangle mesh with premultiplied sampling."""
    rgba=np.asarray(layer,dtype=np.float64)/255
    rgba[:,:,:3]*=rgba[:,:,3:4]
    axis=np.unique(np.r_[np.arange(0,SIZE,8),SIZE-1]).astype(float)
    xx,yy=np.meshgrid(axis,axis)
    src=np.stack((xx.ravel(),yy.ravel()),axis=1)
    dst=deform(src)
    output=np.zeros_like(rgba)
    n=len(axis)
    for row in range(n-1):
        for col in range(n-1):
            indices=(row*n+col,row*n+col+1,(row+1)*n+col,(row+1)*n+col+1)
            # Transparent source cells need no raster work.
            l,t=int(axis[col]),int(axis[row]); r,b=int(axis[col+1]),int(axis[row+1])
            if not rgba[t:b+1,l:r+1,3].any(): continue
            for tri in ((indices[0],indices[1],indices[2]),(indices[1],indices[3],indices[2])):
                s=src[list(tri)]; d=dst[list(tri)]
                matrix=np.column_stack((d[1]-d[0],d[2]-d[0]))
                if abs(np.linalg.det(matrix))<1e-8: continue
                left,top=np.maximum(0,np.floor(d.min(axis=0)).astype(int))
                right,bottom=np.minimum(SIZE-1,np.ceil(d.max(axis=0)).astype(int))
                if right<left or bottom<top: continue
                gx,gy=np.meshgrid(np.arange(left,right+1),np.arange(top,bottom+1))
                query=np.stack((gx.ravel(),gy.ravel()),axis=1)
                uv=(query-d[0])@np.linalg.inv(matrix).T
                inside=(uv[:,0]>=-1e-7)&(uv[:,1]>=-1e-7)&(uv.sum(axis=1)<=1+1e-7)
                q=query[inside]
                sample=s[0]+uv[inside]@np.stack((s[1]-s[0],s[2]-s[0]))
                sample=np.clip(sample,0,SIZE-1)
                lo=np.floor(sample).astype(int); hi=np.minimum(lo+1,SIZE-1); f=sample-lo
                values=(rgba[lo[:,1],lo[:,0]]*((1-f[:,0])*(1-f[:,1]))[:,None]
                        +rgba[lo[:,1],hi[:,0]]*(f[:,0]*(1-f[:,1]))[:,None]
                        +rgba[hi[:,1],lo[:,0]]*((1-f[:,0])*f[:,1])[:,None]
                        +rgba[hi[:,1],hi[:,0]]*(f[:,0]*f[:,1])[:,None])
                # Folded joints can overlap. Transparent texels must not erase
                # an already covered part of the same fur patch.
                existing=output[q[:,1],q[:,0]]
                replace=values[:,3]>=existing[:,3]
                output[q[replace,1],q[replace,0]]=values[replace]
    alpha=output[:,:,3:4]
    output[:,:,:3]=np.divide(output[:,:,:3],alpha,out=np.zeros_like(output[:,:,:3]),where=alpha>0)
    return Image.fromarray(np.uint8(np.clip(np.rint(output*255),0,255)))


def render(layers: dict[str,Image.Image], phase: float) -> tuple[Image.Image,dict]:
    result=Image.new('RGBA',(SIZE,SIZE))
    rendered={}; evidence={}
    for name,kind,onset,x,y,ground,scale,shade in LEGS:
        root=np.array([x,y+float(body_dy(x,phase))])
        paw,contact=foot(phase,onset,x,ground)
        target=joints(kind,root,paw,scale)
        limb=warp(layers[kind],lambda p:skin(p,ANCHORS[kind],target,scale))
        if shade!=1:
            a=np.array(limb);a[:,:,:3]=np.rint(a[:,:,:3]*shade).astype(np.uint8);limb=Image.fromarray(a)
        rendered[name]=limb
        evidence[name]={'controls':target.tolist(),'planned_support':contact,
                        'nominal_foot_bottom':[float(paw[0]),float(paw[1]+8*scale)]}
    def shift_body(p):
        q=p.copy();q[:,1]+=body_dy(q[:,0],phase);return q
    body=warp(layers['body'],shift_body)
    def tail_shift(p):
        pivot=np.array([86.,131.]);a=math.radians(5)*math.sin(2*math.pi*(phase-.12))
        rotation=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
        return (p-pivot)@rotation.T+pivot+np.array([0,float(body_dy(66,phase))])
    tail=warp(layers['tail'],tail_shift)
    head=warp(layers['head'],lambda p:p+np.array([0,float(body_dy(156,phase))*.65]))
    for layer in (rendered['far_hind'],rendered['far_fore'],tail,rendered['near_hind'],rendered['near_fore'],body,head):
        result.alpha_composite(layer)
    return result,evidence


def build(output: Path) -> dict:
    if output.exists(): raise FileExistsError(output)
    baseline=ROOT/'codex_pet/assets/akita'
    record=json.loads((HERE/'source.json').read_text())
    if hashlib.sha256((HERE/'source.png').read_bytes()).hexdigest()!=record['sha256']:
        raise ValueError('Archived source changed')
    for name,sha in record['production_assets'].items():
        if hashlib.sha256((baseline/name).read_bytes()).hexdigest()!=sha:
            raise ValueError(f'Baseline changed: {name}; review and version the experiment')
    source=Image.open(HERE/'source.png').convert('RGBA')
    layers={name:cut(source,name) for name in POLYGONS}
    shutil.copytree(baseline,output)
    review=output/'review';review.mkdir()
    for name,layer in layers.items(): layer.save(review/f'layer-{name}.png')
    manifest=json.loads((output/'pet.json').read_text())
    manifest.update(id=PET_ID,display_name='Akita Cutout · 实验',description='Original Akita textures with an offline articulated run; rejected after user comparison.')
    manifest['frames']={k:v for k,v in manifest['frames'].items() if not k.startswith('running/')}
    frames=[];measurements=[]
    for i in range(PERIOD_MS//FRAME_MS):
        frame,data=render(layers,i*FRAME_MS/PERIOD_MS)
        name=f'running/{i:02}'
        frame.save(output/f'frames/{name}.png')
        manifest['frames'][name]={'file':f'frames/{name}.png'}
        frames.append({'frame':name,'duration_ms':FRAME_MS})
        measurements.append({'time_ms':i*FRAME_MS,'legs':data})
    manifest['clips']['running']['frames']=frames
    (output/'pet.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(output/'frames/running/00.png',output/'running.png')
    (output/'CREDITS.md').write_text('Original Akita pixels from termux-codex-pet 12de0b4. Offline cutout experiment explicitly authorized by the user. New ID; production Akita unchanged. Recipe: docs/artwork/akita/2026-10-cutout/. Rejected by the user: no improvement.\n')
    (review/'motion.json').write_text(json.dumps(measurements,indent=2)+'\n')
    from codex_pet.pet_pack import compile_pack
    compiled=compile_pack(output/'pet.json',validate_images=True)
    result={'id':compiled.id,'period_ms':PERIOD_MS,'frame_ms':FRAME_MS,'frame_count':len(frames),
            'files':{str(f.relative_to(output)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(output.rglob('*')) if f.is_file()}}
    (output/'import-record.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=build(args.output)
    print(json.dumps({k:v for k,v in report.items() if k!='files'}))
