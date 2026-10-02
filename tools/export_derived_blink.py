#!/usr/bin/env python3
"""Reproduce the accepted face-only blink as a static pack asset."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codex_pet.image_codec import decode_png, encode_png


def export(destination: Path) -> None:
    root = ROOT / 'codex_pet/assets/akita/frames/idle'
    width, height, pixels = decode_png((root / '00.png').read_bytes())
    w, h, patch = decode_png((root / '02.png').read_bytes())
    if (width, height) != (256,256) or (w,h) != (width,height):
        raise ValueError('Blink sources must retain the accepted 256-square canvas')
    x0,y0,x1,y1 = 58,54,198,116
    for y in range(y0,y1):
        start,end = (y*width+x0)*4,(y*width+x1)*4
        pixels[start:end] = patch[start:end]
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(encode_png(width,height,pixels))


if __name__ == '__main__':
    export(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'codex_pet/assets/akita/derived/ready-blink.png')
