#!/usr/bin/env python3
"""Reproduce the independent CC0 Pixel Dog pack from the archived sprite sheet."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image

SOURCE = Path(__file__).resolve().parents[1] / 'docs/artwork/pixel_dog/2026-10-import'
SOURCE_SHA256 = '77a32e17840c921f939a754cc5d73622334e568a0bc2c40d55d534b487d2a58a'
ROWS = (('bark', 0, 4), ('running', 2, 5), ('sit', 3, 3),
        ('sitting', 4, 4), ('standing', 5, 4))


def exposures(name: str, count: int, milliseconds: int) -> list[dict]:
    return [{'frame': f'{name}/{i:02d}', 'duration_ms': milliseconds} for i in range(count)]


def export(output: Path) -> None:
    data = (SOURCE / 'dog_medium.png').read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('Archived source differs from the reviewed sheet')
    # Refuse to overwrite a pack or other existing directory, including symlinks.
    output.mkdir(parents=True, exist_ok=False)
    frames, records = {}, {}
    with Image.open(SOURCE / 'dog_medium.png') as sheet:
        if sheet.mode != 'RGBA' or sheet.size != (360, 228):
            raise ValueError('Expected the original 6×6 RGBA sheet')
        for name, row, count in ROWS:
            folder = output / 'frames' / name
            folder.mkdir(parents=True)
            for column in range(count):
                ref = f'{name}/{column:02d}'
                rect = (column * 60, row * 38, (column + 1) * 60, (row + 1) * 38)
                with sheet.crop(rect) as cell, Image.new('RGBA', (64, 64)) as frame:
                    if not cell.getbbox():
                        raise ValueError(f'Unexpected blank source cell: {ref}')
                    frame.paste(cell, (2, 13))
                    path = output / 'frames' / f'{ref}.png'
                    frame.save(path)
                    frames[ref] = {'file': path.relative_to(output).as_posix()}
                    records[ref] = {'source_rect': rect, 'offset': [2, 13],
                                    'png_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                    'rgba_sha256': hashlib.sha256(frame.tobytes()).hexdigest()}

    clips = {
        'idle': {'frames': exposures('standing', 4, 200), 'end': {'mode': 'loop'}},
        'running': {'frames': exposures('running', 5, 130), 'end': {'mode': 'loop'}},
        'needs_input': {'frames': exposures('bark', 4, 150) + exposures('standing', 1, 800),
                        'end': {'mode': 'loop'}},
        'sit_down': {'frames': exposures('sit', 3, 140), 'end': {'mode': 'next', 'clip': 'sitting'}},
        'sitting': {'frames': exposures('sitting', 4, 200), 'end': {'mode': 'loop'}},
        'blocked_entry': {'frames': exposures('sit', 3, 140),
                          'end': {'mode': 'next', 'clip': 'blocked_hold'}},
        'blocked_hold': {'frames': [{'frame': 'sitting/00', 'duration_ms': None}],
                         'end': {'mode': 'hold'}},
    }
    roles = {'idle': 'idle', 'running': 'running', 'needs_input': 'needs_input',
             'ready': 'sit_down', 'blocked': 'blocked_entry'}
    manifest = {'schema_version': 1, 'id': 'pixel_dog', 'canvas_px': [64, 64],
                'display_dp': [64, 64], 'color_space': 'srgb', 'source': {'kind': 'png_directory'},
                'frames': frames, 'clips': clips, 'roles': roles, 'transitions': [],
                'decorations': {'count': {'style': 'robot_count_v1', 'visible_above': 1, 'clamp': 10}}}
    for role, clip in roles.items():
        first = clips[clip]['frames'][0]['frame']
        shutil.copyfile(output / 'frames' / f'{first}.png', output / f'{role}.png')
    timing = {}
    for name in ('Shepherdrun.gif', 'Shepherdbark.gif'):
        with Image.open(SOURCE / name) as gif:
            durations = []
            for index in range(gif.n_frames):
                gif.seek(index)
                durations.append(gif.info['duration'])
        timing[name] = {'sha256': hashlib.sha256((SOURCE / name).read_bytes()).hexdigest(),
                        'durations_ms': durations}
    record = {'source_sha256': SOURCE_SHA256, 'source_size': [360, 228],
              'canvas_px': [64, 64], 'frames': records, 'ancestor_timing': timing}
    for name, value in (('pet.json', manifest), ('import-record.json', record)):
        (output / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    for name in ('CREDITS.md', 'LICENSE.txt'):
        shutil.copyfile(SOURCE / name, output / name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New pack directory; must not exist')
    args = parser.parse_args()
    export(args.output)
    print(f'Exported Pixel Dog to {args.output}')
