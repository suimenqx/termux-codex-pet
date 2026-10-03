"""Grok run video -> stabilised, matted, seamless loop -> pet frames + videos."""
import numpy as np, cv2, json, os, shutil, hashlib, subprocess, sys
from PIL import Image
from matte import matte
SRC='f'; START=int(sys.argv[1]) if len(sys.argv)>1 else 73; P=20; FPS_SRC=24
OUT='out'; shutil.rmtree(OUT,ignore_errors=True)
for d in ('hd','frames_256','review','video'): os.makedirs(f'{OUT}/{d}')
idx=[START+k for k in range(P)]
M=[matte(np.array(Image.open(f'{SRC}/{i+1:04d}.png').convert('RGB')))[0] for i in idx]
# --- stabilisation: the face (upper-right region of the silhouette) should not drift; keep the body bob.
def head_anchor(m):
    a=m[...,3]>128; ys,xs=np.where(a); x1=xs.max(); y0=ys.min()
    reg=a.copy(); reg[:, :int(x1-0.42*(x1-xs.min()))]=0; reg[int(y0+0.55*(ys.max()-y0)):]=0
    yy,xx=np.where(reg); return np.array([xx.mean(), yy.mean()])
def ground(m):
    a=m[...,3]>128; ys,xs=np.where(a); return ys.max()
H=np.array([head_anchor(m) for m in M]); G=np.array([ground(m) for m in M])
# horizontal: lock the head x (treadmill run). vertical: keep the natural bob around the mean.
tx=H[:,0].mean()-H[:,0]
bob=H[:,1]-H[:,1].mean(); ty=-(H[:,1]-H[:,1].mean())+0.6*bob     # keep 60% of the head bob
print('head x range',np.ptp(H[:,0]).round(1),'head y range',np.ptp(H[:,1]).round(1))
S=544
St=[]
for m,dx,dy in zip(M,tx,ty):
    p=m.astype(np.float32)/255; p[...,:3]*=p[...,3:4]
    A=np.float32([[1,0,dx],[0,1,dy]])
    St.append(cv2.warpAffine(p,A,(S,S),flags=cv2.INTER_CUBIC,borderValue=0).clip(0,1))
# --- seam: crossfade nothing (no ghosting); check seam distance
def d(a,b): return np.abs(a-b).mean()*255
print('seam',round(d(St[-1],St[0]),2),'mean step',round(np.mean([d(St[i],St[i+1]) for i in range(P-1)]),2))
# --- common crop for all frames: union bbox, square, padded
U=np.zeros((S,S),bool)
for p in St: U|=p[...,3]>0.02
ys,xs=np.where(U); cx=(xs.min()+xs.max())/2; cy=(ys.min()+ys.max())/2; side=int(max(np.ptp(xs),np.ptp(ys))*1.08)+2
x0=int(round(cx-side/2)); y0=int(round(cy-side/2))
def crop(p):
    c=np.zeros((side,side,4),np.float32); sx0,sy0=max(x0,0),max(y0,0); sx1,sy1=min(x0+side,S),min(y0+side,S)
    c[sy0-y0:sy1-y0, sx0-x0:sx1-x0]=p[sy0:sy1,sx0:sx1]; return c
def unp(p):
    a=p[...,3:4]; rgb=np.where(a>1e-4,p[...,:3]/np.maximum(a,1e-4),0)
    o=(np.clip(np.concatenate([rgb,a],2),0,1)*255+0.5).astype(np.uint8); o[o[...,3]==0]=0; return o
C=[crop(p) for p in St]
ms=round(1000/FPS_SRC*1)  # 41.67 ms per source frame
dur=[42 if k%3!=2 else 41 for k in range(P)]      # 42,42,41 ... sums to 833 ms = 20 frames @24fps
man=[]
for k,p in enumerate(C):
    hd=cv2.resize(p,(768,768),interpolation=cv2.INTER_CUBIC if side<768 else cv2.INTER_AREA).clip(0,1)
    Image.fromarray(unp(hd)).save(f'{OUT}/hd/{k:02d}.png')
    sm=cv2.resize(p,(256,256),interpolation=cv2.INTER_AREA)
    fn=f'{OUT}/frames_256/{k:02d}.png'; Image.fromarray(unp(sm),'RGBA').save(fn)
    man.append({"file":f"{k:02d}.png","seconds":dur[k]/1000,"sha256":hashlib.sha256(open(fn,'rb').read()).hexdigest()})
json.dump({"frames":man},open(f'{OUT}/frames_256/frames.json','w'),indent=1)
json.dump({"clips":{"running":{"frames":[{"frame":f"running/{k:02d}","duration_ms":dur[k]} for k in range(P)],"end":{"mode":"loop"}}},
           "source":{"video":"Grok generated_video.mp4","fps":24,"frames_used":[i for i in idx],"cycle_ms":sum(dur)},
           "note":"frames are the original video frames: matted, head-stabilised (60% of head bob kept), uniformly cropped; no interpolation"},
          open(f'{OUT}/pet-clips-running.json','w'),indent=1)
print('side',side,'cycle ms',sum(dur))
