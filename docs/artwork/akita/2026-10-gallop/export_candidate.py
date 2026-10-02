"""Export the generated candidate using one measured model registration.

No per-pose zoom, recentering, limb deformation or runtime compensation.
The shared registration matches the eye distance and midpoint of the original
running model. It does not certify gait or compensate for changing head shape.
"""
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from tools.historical_art import _decode_rgba_png, _png

# Centers of dark eye regions in normalized 256 px views; manual correspondence
# checked against the source images. Coordinates have about 1 px annotation error.
REFERENCE_EYES = ((182.5, 108.0), (216.5, 109.0))
CANDIDATE_EYES = ((188.0, 86.0), (227.0, 86.0))
SCALE = (REFERENCE_EYES[1][0] - REFERENCE_EYES[0][0]) / (
    CANDIDATE_EYES[1][0] - CANDIDATE_EYES[0][0])
OFFSET = tuple(sum(p[i] for p in REFERENCE_EYES)/2 -
               SCALE*sum(p[i] for p in CANDIDATE_EYES)/2 for i in range(2))

@lru_cache(maxsize=5)
def source(name):
    return _decode_rgba_png((HERE/name).read_bytes())

def export_frame(index):
    name = f'segment-{"abcd"[index//4]}.png'
    cell = index % 4
    columns = rows = 2
    if index == 10:
        name, cell, columns, rows = 'support-inbetween.png', 0, 1, 1
    width, height, pixels = source(name)
    if width*rows != height*columns:
        raise ValueError('source grid must have square cells')
    size = width/columns
    left, top = (cell % columns)*size, (cell//columns)*size
    out = bytearray(256*256*4)
    for y in range(256):
        for x in range(256):
            u = ((x+.5-OFFSET[0])/SCALE)/256
            v = ((y+.5-OFFSET[1])/SCALE)/256
            if not (0 <= u < 1 and 0 <= v < 1):
                continue
            sx, sy = left+u*size-.5, top+v*size-.5
            ix, iy = math.floor(sx), math.floor(sy)
            fx, fy = sx-ix, sy-iy
            a = 0.0
            rgb = [0.0]*3
            for dx,dy,weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),
                                 (0,1,(1-fx)*fy),(1,1,fx*fy)):
                xx, yy = ix+dx, iy+dy
                if not (left <= xx+.5 < left+size and top <= yy+.5 < top+size):
                    continue
                k = (yy*width+xx)*4
                alpha = pixels[k+3]/255*weight
                a += alpha
                for channel in range(3):
                    rgb[channel] += pixels[k+channel]*alpha
            k = (y*256+x)*4
            if a:
                out[k:k+3] = bytes(min(255,round(c/a)) for c in rgb)
                out[k+3] = min(255,round(a*255))
    return _png(256,256,out)

def main():
    destination = Path(sys.argv[1])
    destination.mkdir(parents=True, exist_ok=True)
    frames = []
    for index in range(16):
        image = export_frame(index)
        name = f'{index:02}.png'
        (destination/name).write_bytes(image)
        frames.append(dict(file=name, seconds=.04,
                           sha256=hashlib.sha256(image).hexdigest()))
    (destination/'frames.json').write_text(json.dumps(dict(frames=frames),indent=2)+'\n')
    print(json.dumps(dict(scale=SCALE, offset=OFFSET, frames=len(frames))))

if __name__ == '__main__':
    main()
