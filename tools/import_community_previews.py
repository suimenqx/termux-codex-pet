#!/usr/bin/env python3
"""Build five local preview packs from the hash-locked original source archive.

No source art is distributed by this repository. --download fetches only the
listed public source URLs; normal execution uses an existing private archive.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import urllib.request

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_pet.pet_pack import compile_pack  # noqa: E402

LOCK = Path(__file__).resolve().parents[1] / 'docs/artwork/community_previews/2026-10-import/sources.json'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shrink(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return image.convert('RGBa').resize(size, Image.Resampling.LANCZOS).convert('RGBA')


def bongo_poses(root: Path) -> dict[str, Image.Image]:
    # Authored CSS table closes the originally transparent white-site body.
    table = Image.new('RGBA', (3200, 1800))
    angle = math.radians(13.5)
    points = []
    for x, y in ((-800, -2.5), (800, -2.5), (800, 2.5), (-800, 2.5)):
        points.append(((400 + x * math.cos(angle) - y * math.sin(angle)) * 4,
                       (142.5 + x * math.sin(angle) + y * math.cos(angle)) * 4))
    ImageDraw.Draw(table).polygon(points, fill='black')
    table = shrink(table, (800, 450))
    layers = {}
    for name in ('cat', 'mouth', 'bongo', 'paw-left', 'paw-right'):
        with Image.open(root / 'images' / f'{name}.png') as source:
            layers[name] = source.convert('RGBA')
    result = {}
    for name, left, right, mouth in (('idle', 0, 0, 0), ('tap_left', 1, 0, 0),
                                    ('tap_right', 0, 1, 0), ('tap_both', 1, 1, 0), ('meow', 0, 0, 1)):
        stage = table.copy()
        for layer, column in (('cat', 0), ('mouth', mouth), ('bongo', 0),
                              ('paw-left', left), ('paw-right', right)):
            stage.alpha_composite(layers[layer].crop((column * 800, 0, (column + 1) * 800, 450)))
        alpha = stage.getchannel('A').tobytes()
        outside = bytearray(800 * 450)
        queue: deque[int] = deque()
        def visit(index: int) -> None:
            if not alpha[index] and not outside[index]:
                outside[index] = 1
                queue.append(index)
        for x in range(800):
            visit(x)
            visit(449 * 800 + x)
        for y in range(450):
            visit(y * 800)
            visit(y * 800 + 799)
        while queue:
            index = queue.popleft()
            x, y = index % 800, index // 800
            if x: visit(index - 1)
            if x < 799: visit(index + 1)
            if y: visit(index - 800)
            if y < 449: visit(index + 800)
        fill = Image.new('RGBA', stage.size, 'white')
        fill.putalpha(Image.frombytes('L', stage.size,
                      bytes(255 if not a and not out else 0 for a, out in zip(alpha, outside))))
        fill.alpha_composite(stage)
        square = Image.new('RGBA', (460, 460))
        square.paste(fill.crop((240, 0, 700, 414)), (0, 23))
        result[name] = shrink(square, (256, 256))
    return result


class Pack:
    def __init__(self, output: Path, ident: str, name: str, description: str):
        self.folder = output / ident
        self.folder.mkdir()
        self.frames: dict = {}
        self.records: dict = {}
        self.clips: dict = {}
        self.manifest = {'schema_version': 1, 'id': ident, 'display_name': name,
                         'description': description, 'canvas_px': [256, 256], 'display_dp': [64, 64],
                         'color_space': 'srgb', 'source': {'kind': 'png_directory'},
                         'frames': self.frames, 'clips': self.clips, 'transitions': [],
                         'decorations': {'count': {'style': 'akita_count_v1', 'visible_above': 1, 'clamp': 10}}}

    def frame(self, ref: str, image: Image.Image, source: str) -> None:
        if image.mode != 'RGBA' or image.size != (256, 256) or image.getbbox() is None:
            raise ValueError(f'Invalid/blank output frame {ref}')
        path = self.folder / 'frames' / f'{ref}.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        self.frames[ref] = {'file': path.relative_to(self.folder).as_posix()}
        self.records[ref] = {'source': source, 'png_sha256': digest(path),
                             'rgba_sha256': hashlib.sha256(image.tobytes()).hexdigest()}

    def clip(self, name: str, frames: list[tuple[str, int | None]], end: str = 'loop') -> None:
        finish = {'mode': end} if end in ('loop', 'hold') else {'mode': 'next', 'clip': end}
        self.clips[name] = {'frames': [{'frame': ref, 'duration_ms': ms} for ref, ms in frames],
                            'end': finish}

    def finish(self, roles: dict, credits: str) -> None:
        self.manifest['roles'] = roles
        (self.folder / 'pet.json').write_text(json.dumps(self.manifest, indent=2) + '\n')
        (self.folder / 'import-record.json').write_text(json.dumps(self.records, indent=2) + '\n')
        (self.folder / 'CREDITS.md').write_text(credits, encoding='utf-8')
        compile_pack(self.folder / 'pet.json', validate_images=True)
        print(f'{self.manifest["id"]}: {len(self.frames)} validated frames', flush=True)


def export(sources: Path, output: Path, download: bool = False) -> None:
    lock = json.loads(LOCK.read_text())
    for relative, record in lock['files'].items():
        path = sources / relative
        if download and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(record['url'], timeout=45) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError(f'Download hash mismatch: {relative}')
            path.write_bytes(data)
        if digest(path) != record['sha256']:
            raise ValueError(f'Source hash mismatch: {relative}')
    output.mkdir(parents=True, exist_ok=False)
    roles = {name: name for name in ('idle', 'running', 'needs_input', 'ready', 'blocked')}
    for slug in ('boba', 'mochi', 'golden-retriever'):
        meta = lock['pets'][slug]
        pack = Pack(output, slug.replace('-', '_'), meta['name'], meta['description'])
        with Image.open(sources / f'{slug}-sheet.webp') as source:
            sheet = source.convert('RGBA')
        if sheet.size != tuple(meta['source_size']):
            raise ValueError('Unexpected Petdex sheet size')
        for name, row, times in (('idle', 0, [280, 110, 110, 140, 140, 320]),
                                 ('running', 1, [120] * 7 + [220]),
                                 ('needs_input', 3, [140] * 3 + [280]),
                                 ('ready', 4, [140] * 4 + [280]),
                                 ('blocked', 5, [140] * 7 + [240])):
            clip = []
            for index, ms in enumerate(times):
                rect = (index * 192, row * 208, (index + 1) * 192, (row + 1) * 208)
                frame = Image.new('RGBA', (256, 256))
                frame.paste(sheet.crop(rect), (32, 24))
                ref = f'{name}/{index:02d}'
                pack.frame(ref, frame, f'{slug}-sheet.webp rect={rect}; paste=(32,24)')
                clip.append((ref, ms))
            end = 'idle' if name == 'ready' else 'blocked_hold' if name == 'blocked' else 'loop'
            pack.clip(name, clip, end)
        pack.clip('blocked_hold', [('blocked/07', None)], 'hold')
        pack.finish(roles, meta['credits'])

    pack = Pack(output, 'vpet', 'VPet', 'Original VPet vup animations: https://github.com/LorisYounger/VPet (local noncommercial preview).')
    folders = {'idle': 'Default/Nomal/1', 'walk_in': 'MOVE/walk.left.faster/A_Happy',
               'running': 'MOVE/walk.left.faster/B_Happy', 'walk_out': 'MOVE/walk.left.faster/C_Happy',
               'think_in': 'Think/Nomal/A', 'thinking': 'Think/Nomal/B',
               'touch_in': 'Touch_Head/A_Nomal', 'touching': 'Touch_Head/B_Nomal',
               'touch_out': 'Touch_Head/C_Nomal'}
    sequences = {}
    for clip, folder in folders.items():
        frames = []
        names = sorted(path for path in lock['files'] if path.startswith(f'vpet/{folder}/') and path.endswith('.png'))
        for index, name in enumerate(names):
            ref = f'{clip}/{index:02d}'
            with Image.open(sources / name) as image:
                if image.size != (1000, 1000): raise ValueError('Expected 1000px VPet source')
                pack.frame(ref, shrink(image.convert('RGBA'), (256, 256)), name + '; whole canvas 1000→256')
            frames.append((ref, int(Path(name).stem.rsplit('_', 1)[1])))
        if not frames: raise ValueError(f'Empty source clip: {clip}')
        sequences[clip] = frames
        next_clip = {'walk_in': 'running', 'walk_out': 'touch_in', 'think_in': 'thinking',
                     'touch_in': 'touching', 'touching': 'touch_out', 'touch_out': 'idle'}.get(clip, 'loop')
        pack.clip(clip, frames, next_clip)
    pack.clip('blocked', sequences['think_in'] + sequences['thinking'], 'blocked_hold')
    pack.clip('blocked_hold', [(sequences['thinking'][-1][0], None)], 'hold')
    pack.manifest['transitions'] = [{'from': 'running', 'to': 'ready', 'clip': 'walk_out'}]
    pack.finish({'idle': 'idle', 'running': 'walk_in', 'needs_input': 'think_in',
                 'ready': 'touch_in', 'blocked': 'blocked'}, lock['pets']['vpet']['credits'])
    shutil.copyfile(sources / 'vpet-readme.txt', pack.folder / 'LICENSE.md')

    pack = Pack(output, 'bongo_cat', 'Bongo Cat Classic', 'Classic bongo.cat drumming layers; local preview, not the Live2D edition.')
    for name, frame in bongo_poses(sources / 'bongo-classic').items():
        pack.frame(name, frame, 'Original bongo.cat PNG layers + CSS table; fixed crop/padding; see brief')
    pack.clip('idle', [('idle', None)], 'hold')
    pack.clip('running', [('tap_left', 100), ('idle', 80), ('tap_right', 100), ('idle', 80)])
    pack.clip('needs_input', [('meow', 300), ('idle', 700)])
    pack.clip('ready', [('tap_both', 160), ('idle', 160)] * 2, 'idle')
    pack.clip('blocked', [('meow', None)], 'hold')
    pack.finish(roles, lock['pets']['bongo_cat']['credits'] + '\n' + (sources / 'bongo-classic/README.md').read_text())
    shutil.copyfile(sources / 'bongo-classic/LICENSE', pack.folder / 'LICENSE.txt')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download', action='store_true', help='Fetch missing locked sources over HTTPS')
    args = parser.parse_args()
    export(args.sources, args.output, args.download)
