"""Draw technical pose references only; these are never runtime pet artwork."""
from pathlib import Path
import math
import sys
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from codex_pet.art import _png
p = Path(__file__).resolve().parent
poses={6:{'hind_far':[(99,156),(90,178),(73,202),(91,218)],'fore_far':[(190,161),(201,175),(191,178),(198,185)],'hind_near':[(76,158),(111,179),(100,197),(121,211)],'fore_near':[(149,165),(166,179),(161,183),(175,190)]},7:{'hind_far':[(99,156),(76,182),(48,204),(59,218)],'fore_far':[(190,161),(208,180),(204,193),(209,200)],'hind_near':[(76,158),(116,184),(104,214),(117,225)],'fore_near':[(149,165),(174,185),(177,193),(182,199)]}}
colors={'hind_far':(45,150,170,255),'hind_near':(220,50,140,255),'fore_far':(190,145,35,255),'fore_near':(70,170,55,255)}
for i,legs in poses.items():
 size=768; data=bytearray([247,247,247,255]*(size*size))
 def ellipse(cx,cy,rx,ry,col):
  cx*=3;cy*=3;rx*=3;ry*=3
  for y in range(max(0,int(cy-ry)),min(size,int(cy+ry+1))):
   for x in range(max(0,int(cx-rx)),min(size,int(cx+rx+1))):
    if ((x-cx)/rx)**2+((y-cy)/ry)**2<=1:
     q=(y*size+x)*4;data[q:q+4]=bytes(col)
 def line(a,b,col,width):
  steps=int(math.dist(a,b)*3)+1
  for n in range(steps+1):
   t=n/steps;ellipse(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,width/2,width/2,col)
 ellipse(102,155,60,31,(219,219,219,255));ellipse(173,111,61,57,(228,228,228,255));ellipse(64,110,29,28,(228,228,228,255))
 line((10,234),(249,234),(190,190,190,255),1)
 for name,chain in legs.items():
  color=colors[name];width=10 if 'far' in name else 14
  for a,b in zip(chain,chain[1:]):line(a,b,color,width)
  ellipse(*chain[-1],11,7,color)
 (p/f'pose-{i:02}-guide.png').write_bytes(_png(size,size,data))
(p/'guide-landmarks.json').write_text(__import__('json').dumps(poses,indent=2)+'\n')
