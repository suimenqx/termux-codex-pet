"""Validate and compile data-only pet packs without importing image or GUI code."""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

ROLES = frozenset(('idle', 'running', 'needs_input', 'ready', 'blocked'))
MAX_DECODE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


@dataclass(frozen=True)
class FrameDefinition:
    file: Path | None = None
    pose: str = ''
    variant: int = 0


@dataclass(frozen=True)
class Clip:
    name: str
    references: tuple[str, ...]
    durations_ns: tuple[int | None, ...]
    ends_ns: tuple[int, ...]
    mode: str
    next_clip: str | None

    @property
    def duration_ns(self) -> int:
        return self.ends_ns[-1]


@dataclass(frozen=True)
class PetPack:
    id: str
    revision: str
    canvas: tuple[int, int]
    display: tuple[int, int]
    frames: Mapping[str, FrameDefinition]
    clips: Mapping[str, Clip]
    roles: Mapping[str, str]
    transitions: Mapping[tuple[str, str], str]
    decoration: str

    def entry(self, state: str, source: str | None = None) -> str:
        state = state if state in self.roles else 'idle'
        return self.transitions.get((source, state), self.roles[state]) if source else self.roles[state]


def _positive(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f'{name} must be a positive integer')
    return value


def _dimensions(value: Any, name: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f'{name} must contain width and height')
    return _positive(value[0], name), _positive(value[1], name)


def _mapping(value: Any, name: str) -> dict:
    if not isinstance(value, dict) or not value:
        raise ValueError(f'{name} must be a nonempty object')
    return value


def compile_pack(manifest: Path, *, validate_images: bool = False) -> PetPack:
    try:
        if manifest.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError('Manifest exceeds byte budget')
        raw = manifest.read_bytes()
        data = _mapping(json.loads(raw), 'manifest')
        if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
            raise ValueError('Unsupported pet pack schema_version')
        pack_id = data.get('id')
        if not isinstance(pack_id, str) or not pack_id or len(pack_id) > 100:
            raise ValueError('Invalid pet pack id')
        canvas = _dimensions(data.get('canvas_px'), 'canvas_px')
        display = _dimensions(data.get('display_dp'), 'display_dp')
        if canvas[0] * canvas[1] * 4 > MAX_DECODE_BYTES:
            raise ValueError('Canvas exceeds decode budget')
        if data.get('color_space', 'srgb') != 'srgb':
            raise ValueError('Only sRGB pet assets are supported')
        source = _mapping(data.get('source'), 'source')
        builtin = source.get('kind') == 'builtin'
        if builtin:
            if source.get('id') != 'robot_v1' or canvas != (64, 64):
                raise ValueError('Unknown builtin or invalid builtin canvas')
        elif source.get('kind') != 'png_directory':
            raise ValueError('Unsupported frame source')
        frames = {}
        root = manifest.parent.resolve()
        for ref, value in _mapping(data.get('frames'), 'frames').items():
            if not isinstance(ref, str) or not ref:
                raise ValueError('Invalid frame reference')
            value = _mapping(value, 'frame')
            if builtin:
                pose, variant = value.get('pose'), value.get('variant')
                if (not isinstance(pose, str) or pose not in ROLES or type(variant) is not int
                        or variant not in range(2 if pose in ('running', 'needs_input') else 1)):
                    raise ValueError('Unknown builtin pose')
                frames[ref] = FrameDefinition(pose=pose, variant=variant)
            else:
                filename = value.get('file')
                if not isinstance(filename, str) or not filename or Path(filename).is_absolute():
                    raise ValueError('Invalid frame file')
                path = (root / filename).resolve()
                if not path.is_relative_to(root):
                    raise ValueError('Frame path escapes pack')
                if not path.is_file():
                    raise ValueError(f'Missing frame {ref}')
                frames[ref] = FrameDefinition(file=path)
        identities = {definition.file or (definition.pose, definition.variant) for definition in frames.values()}
        if len(identities) * canvas[0] * canvas[1] * 4 > MAX_DECODE_BYTES:
            raise ValueError('Pet pack exceeds decoded asset budget')
        clips = {}
        for name, value in _mapping(data.get('clips'), 'clips').items():
            value = _mapping(value, 'clip')
            exposures = value.get('frames')
            end = _mapping(value.get('end'), 'clip end')
            mode = end.get('mode')
            if mode not in ('next', 'loop', 'hold'):
                raise ValueError('Invalid clip ending')
            if not isinstance(exposures, list) or not exposures:
                raise ValueError('Clip needs exposures')
            references, durations, ends = [], [], []
            total = 0
            for exposure in exposures:
                exposure = _mapping(exposure, 'exposure')
                ref = exposure.get('frame')
                if not isinstance(ref, str) or ref not in frames:
                    raise ValueError('Unknown exposure frame')
                duration = exposure.get('duration_ms')
                if duration is None:
                    if mode != 'hold' or len(exposures) != 1:
                        raise ValueError('Only a single-frame hold may omit duration')
                    ns = None
                else:
                    ns = _positive(duration, 'duration_ms') * 1_000_000
                    total += ns
                references.append(ref)
                durations.append(ns)
                ends.append(total)
            target = end.get('clip') if mode == 'next' else None
            if mode == 'next' and not isinstance(target, str):
                raise ValueError('next requires a clip reference')
            clips[name] = Clip(name, tuple(references), tuple(durations), tuple(ends), mode, target)
        for name in clips:
            seen = set()
            current = name
            while True:
                if current not in clips or current in seen:
                    raise ValueError('Invalid or cyclic next relationship')
                seen.add(current)
                clip = clips[current]
                if clip.mode != 'next':
                    break
                assert clip.next_clip is not None
                current = clip.next_clip
        roles = _mapping(data.get('roles'), 'roles')
        if set(roles) != ROLES or any(not isinstance(v, str) or v not in clips for v in roles.values()):
            raise ValueError('Roles must resolve every visible state')
        transitions = {}
        rows = data.get('transitions', [])
        if not isinstance(rows, list):
            raise ValueError('transitions must be a list')
        for row in rows:
            row = _mapping(row, 'transition')
            a, b, target = row.get('from'), row.get('to'), row.get('clip')
            if (not isinstance(a, str) or not isinstance(b, str) or a not in roles or b not in roles
                    or not isinstance(target, str) or target not in clips or (a, b) in transitions):
                raise ValueError('Invalid or duplicate transition')
            transitions[a, b] = target
        decoration = _mapping(_mapping(data.get('decorations'), 'decorations').get('count'), 'count')
        style = decoration.get('style')
        if (style not in ('akita_count_v1', 'robot_count_v1')
                or decoration.get('visible_above') != 1 or decoration.get('clamp') != 10):
            raise ValueError('Unsupported count decoration')
        if style == 'robot_count_v1' and canvas != (64,64):
            raise ValueError('robot_count_v1 requires a 64-square canvas')
        pack = PetPack(pack_id, hashlib.sha256(raw).hexdigest(), canvas, display,
                       MappingProxyType(frames), MappingProxyType(clips), MappingProxyType(roles),
                       MappingProxyType(transitions), style)
        if validate_images:
            _validate_images(pack)
        return pack
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError(f'Invalid pet pack {manifest}: {exc}') from exc


def _validate_images(pack: PetPack) -> None:
    from .image_codec import decode_png
    checked = set()
    for definition in pack.frames.values():
        path = definition.file
        if path is None or path in checked:
            continue
        checked.add(path)
        if path.stat().st_size > MAX_DECODE_BYTES:
            raise ValueError('Encoded image exceeds byte budget')
        encoded = path.read_bytes()
        width, height, pixels = decode_png(encoded)
        if (width, height) != pack.canvas or len(pixels) != width * height * 4:
            raise ValueError(f'Frame dimensions differ from pack: {path.name}')


@lru_cache(maxsize=8)
def bundled_pack(pack_id: str) -> PetPack:
    if pack_id not in ('akita', 'robot'):
        raise ValueError('Unknown bundled pack')
    return compile_pack(Path(__file__).parent / 'assets' / pack_id / 'pet.json')


def preflight(package: Path) -> None:
    from .image_codec import check_capability
    check_capability()
    for name in ('robot', 'akita'):
        pack = compile_pack(package / 'assets' / name / 'pet.json', validate_images=True)
        if pack.id != name:
            raise ValueError('Pack id does not match its installed catalog entry')
