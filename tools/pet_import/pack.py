"""Shared validated PNG pack writer for offline importers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from codex_pet.pet_pack import compile_pack


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shrink(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return image.convert("RGBa").resize(size, Image.Resampling.LANCZOS).convert("RGBA")


class Pack:
    def __init__(self, output: Path, ident: str, name: str, description: str, canvas: tuple[int, int] = (256, 256),
                 deduplicate: bool = False):
        self.canvas = canvas
        self.deduplicate = deduplicate
        self.pixel_files: dict[str, Path] = {}
        self.folder = output / ident
        self.folder.mkdir()
        self.frames: dict = {}
        self.records: dict = {}
        self.clips: dict = {}
        self.manifest = {'schema_version': 1, 'id': ident, 'display_name': name,
                         'description': description, 'canvas_px': list(canvas), 'display_dp': [64, 64],
                         'color_space': 'srgb', 'source': {'kind': 'png_directory'},
                         'frames': self.frames, 'clips': self.clips, 'transitions': [],
                         'decorations': {'count': {'style': 'akita_count_v1', 'visible_above': 1, 'clamp': 10}}}

    def frame(self, ref: str, image: Image.Image, source: str) -> None:
        if image.mode != 'RGBA' or image.size != self.canvas or image.getbbox() is None:
            raise ValueError(f'Invalid/blank output frame {ref}')
        rgba_hash = hashlib.sha256(image.tobytes()).hexdigest()
        path = self.pixel_files.get(rgba_hash) if self.deduplicate else None
        if path is None:
            path = self.folder / 'frames' / f'{ref}.png'
            path.parent.mkdir(parents=True, exist_ok=True)
            image.save(path)
            self.pixel_files[rgba_hash] = path
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
