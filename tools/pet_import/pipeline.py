"""Hash-locked source acquisition and transactional recipe-to-pack conversion."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request

from PIL import Image

from codex_pet.image_contract import rgba_size
from codex_pet.pet_pack import MAX_PACK_BYTES

from .decoders import decode
from .pack import Pack, digest, shrink


def fetch_sources(recipe: dict, cache: Path, download: bool) -> dict[str, Path]:
    cache.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, entry in recipe['sources'].items():
        sha = entry['sha256']
        if not re.fullmatch(r'[0-9a-f]{64}', sha) or not entry['url'].startswith('https://'):
            raise ValueError(f'Invalid source lock: {name}')
        path = cache / sha
        if not path.exists() and download:
            # Only publish a verified complete blob. Interrupted downloads cannot
            # become a cache hit, including with two importers sharing a cache.
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as target:
                temporary = Path(target.name)
                try:
                    with urllib.request.urlopen(entry['url'], timeout=45) as response:
                        if not response.url.startswith('https://'):
                            raise ValueError('Source redirected away from HTTPS')
                        shutil.copyfileobj(response, target)
                    target.flush()
                    if digest(temporary) != sha:
                        raise ValueError(f'Download hash mismatch: {name}')
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
        if not path.exists():
            raise ValueError(f'Missing source {name}; use --download or seed {path}')
        if digest(path) != sha:
            raise ValueError(f'Source hash mismatch: {name}')
        result[name] = path
    return result


def layout_frame(image: Image.Image, layout: dict, canvas: tuple[int, int]) -> Image.Image:
    image = image.convert('RGBA')
    if 'crop' in layout:
        image = image.crop(tuple(layout['crop']))
    if 'size' in layout:
        image = shrink(image, tuple(layout['size']))
    result = Image.new('RGBA', canvas)
    x, y = layout.get('offset', [0, 0])
    bounds = image.getbbox()
    if bounds and (bounds[0] + x < 0 or bounds[1] + y < 0 or
                   bounds[2] + x > canvas[0] or bounds[3] + y > canvas[1]):
        raise ValueError(f'Layout clips nontransparent pixels: {bounds}, offset={(x, y)}')
    # Paste copies straight RGBA, without applying alpha a second time.
    result.paste(image, (x, y))
    return result


def build_recipe(recipe_path: Path, cache: Path, output: Path,
                 download: bool = False, canvas_module: Path | None = None) -> Path:
    """Build one new pack, or fail without publishing a partial/replaced pack.

    The recipe is a maintained, trusted repository input, not a user scripting
    language. All material is fetched by pinned SHA; no recipe executes commands.
    """
    recipe = json.loads(recipe_path.read_text())
    ident = recipe['id']
    if recipe.get('version') != 1 or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', ident):
        raise ValueError('Unsupported recipe version or invalid pet ID')
    output.mkdir(parents=True, exist_ok=True)
    destination = output / ident
    with (output / '.build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists():
            raise FileExistsError(f'Pack already exists: {destination}')
        sources = fetch_sources(recipe, cache, download)
        with tempfile.TemporaryDirectory(prefix='.build-', dir=output) as work:
            root = Path(work)
            canvas = tuple(recipe['canvas'])
            rgba_size(*canvas)
            pack = Pack(root, ident, recipe['name'], recipe['description'], canvas, True)
            sequences = {}
            transparent = False
            decoded = 0
            for name, spec in recipe['sequences'].items():
                if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*', name):
                    raise ValueError(f'Invalid sequence name: {name}')
                frames = []
                for index, (image, ms) in enumerate(decode(spec, sources, root, canvas_module)):
                    if type(ms) is not int or ms <= 0:
                        raise ValueError(f'Invalid source exposure: {name}/{index}')
                    frame = layout_frame(image, spec.get('layout', {}), canvas)
                    transparent |= frame.getchannel('A').getextrema()[0] == 0
                    ref = f'{name}/{index:04d}'
                    before = len(pack.pixel_files)
                    pack.frame(ref, frame, f'{name}: source frame {index}; see import-record.json recipe')
                    decoded += (len(pack.pixel_files) - before) * canvas[0] * canvas[1] * 4
                    if decoded > MAX_PACK_BYTES:
                        raise ValueError('Pack exceeds 64 MiB decoded frame budget')
                    frames.append((ref, ms))
                    if index >= 1999:
                        raise ValueError('Sequence exceeds 2000-frame offline limit')
                if not frames:
                    raise ValueError(f'Empty source sequence: {name}')
                sequences[name] = frames
            if not transparent:
                raise ValueError('No transparent pixels in exported pet')
            for name, spec in recipe['clips'].items():
                frames = sequences[spec['sequence']]
                if 'select' in spec:
                    frames = [frames[i] for i in spec['select']]
                if spec.get('hold'):
                    if len(frames) != 1:
                        raise ValueError('An infinite hold requires one selected frame')
                    frames = [(frames[0][0], None)]
                pack.clip(name, frames, spec.get('end', 'loop'))
            credits = recipe['credits'] + '\n\n'
            for source in recipe.get('notices', []):
                encoding = recipe['sources'][source].get('encoding', 'utf-8')
                credits += f'\n## Original notice: {source}\n\n' + sources[source].read_text(encoding=encoding) + '\n'
            pack.finish(recipe['roles'], credits)
            record = {'recipe_sha256': digest(recipe_path), 'recipe': recipe,
                      'decoded_bytes': decoded, 'frames': pack.records,
                      'sequences': {n: {'frames': len(f), 'duration_ms': sum(ms for _, ms in f)}
                                    for n, f in sequences.items()}}
            (pack.folder / 'import-record.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
            pack.folder.rename(destination)
    return destination
