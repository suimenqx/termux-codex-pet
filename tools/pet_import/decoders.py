"""Offline source formats. Each decoder yields composed RGBA and exposure ms."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from PIL import Image, ImageColor


def media_env() -> dict[str, str]:
    env = dict(os.environ)
    if 'PREFIX' in env:
        # Codex can prepend its own older libc++; isolate the ffmpeg child only.
        env['LD_LIBRARY_PATH'] = str(Path(env['PREFIX']) / 'lib')
    return env


def video_frames(path: Path, spec: dict, work: Path):
    env = media_env()
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                            '-show_frames', '-show_streams', '-show_format', '-of', 'json', str(path)],
                           env=env, capture_output=True, check=True, timeout=90)
    data = json.loads(probe.stdout)
    stream = data['streams'][0]
    width, height = stream['width'], stream['height']
    if [width, height] != spec['source_size']:
        raise ValueError('Unexpected video dimensions')
    frames = data['frames']
    points = [round(float(f['best_effort_timestamp_time']) * 1000) for f in frames]
    end = round(float(data['format']['duration']) * 1000)
    if len(points) != spec['frame_count'] or end != spec['duration_ms'] or points[0] != 0:
        raise ValueError('Unexpected video timeline')
    durations = [b - a for a, b in zip(points, points[1:] + [end])]
    step = spec.get('step', 1)
    if type(step) is not int or step <= 0 or any(ms <= 0 for ms in durations):
        raise ValueError('Invalid video sampling/timestamps')
    # Stream frames through a bounded buffer; stderr uses a file to avoid pipe
    # deadlock. Explicit libvpx-vp9 is necessary: native vp9 drops WebM alpha.
    with (work / 'ffmpeg.log').open('w+b') as errors:
        process = subprocess.Popen(['ffmpeg', '-v', 'error', '-c:v', 'libvpx-vp9',
                                    '-i', str(path), '-vsync', '0', '-pix_fmt', 'rgba',
                                    '-f', 'rawvideo', 'pipe:1'], env=env,
                                   stdout=subprocess.PIPE, stderr=errors)
        try:
            assert process.stdout is not None
            count = width * height * 4
            saw_transparency = False
            for i in range(len(points)):
                raw = process.stdout.read(count)
                if len(raw) != count:
                    raise ValueError(f'Truncated video frame {i}')
                if i % step == 0:
                    image = Image.frombytes('RGBA', (width, height), raw)
                    saw_transparency |= image.getchannel('A').getextrema()[0] == 0
                    yield image, sum(durations[i:i + step])
            if process.stdout.read(1):
                raise ValueError('Unexpected extra decoded video frames')
            if process.wait(timeout=30) != 0:
                errors.seek(0)
                raise ValueError(f'ffmpeg failed: {errors.read(2000).decode(errors="replace")}')
            if not saw_transparency:
                raise ValueError('Video alpha was lost during decoding')
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
            process.wait()


def esheep_frames(path: Path, spec: dict):
    root = ET.parse(path).getroot()
    for element in root.iter():
        element.tag = element.tag.split('}')[-1]
    sheet = Image.open(io.BytesIO(base64.b64decode(root.findtext('image/png')))).convert('RGBA')
    columns, rows = int(root.findtext('image/tilesx')), int(root.findtext('image/tilesy'))
    if columns <= 0 or rows <= 0 or sheet.width % columns or sheet.height % rows:
        raise ValueError('Invalid eSheep atlas grid')
    # Preserve existing alpha. Only the exact window color-key becomes clear.
    key = ImageColor.getrgb(root.findtext('image/transparency', 'Magenta'))
    pixels = bytearray(sheet.tobytes())
    for i in range(0, len(pixels), 4):
        if tuple(pixels[i:i + 3]) == key:
            pixels[i + 3] = 0
    sheet = Image.frombytes('RGBA', sheet.size, bytes(pixels))
    animation = next(a for a in root.findall('animations/animation')
                     if a.get('id') == str(spec['animation']))
    start, end = animation.findtext('start/interval'), animation.findtext('end/interval')
    if start != end or not start or not start.isdecimal() or int(start) <= 0:
        raise ValueError('eSheep extraction supports equal positive literal intervals only')
    width, height = sheet.width // columns, sheet.height // rows
    for entry in animation.findall('sequence/frame'):
        index = int(entry.text)
        if not 0 <= index < columns * rows:
            raise ValueError('eSheep tile index outside atlas')
        x, y = index % columns * width, index // columns * height
        yield sheet.crop((x, y, x + width, y + height)), int(start)


def spine_frames(spec: dict, sources: dict, work: Path, canvas_module: Path | None):
    if canvas_module is None or not (canvas_module / 'package.json').is_file():
        raise ValueError('Spine export needs --setup-spine or --canvas-module; see community_pets/README.md')
    settings = {k: v for k, v in spec.items() if k not in ('animation', 'layout')}
    key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()[:16]
    stage = work / ('spine-' + key)
    stage.mkdir(exist_ok=True)
    output = stage / 'frames'
    report = output / 'report.json'
    if not report.exists():
        with Image.open(sources[spec['texture']]) as source:
            rgba = source.convert('RGBA')
            # Source is premultiplied RGBA in PNG: unpremultiply before Canvas.
            straight = Image.frombytes('RGBa', rgba.size, rgba.tobytes()).convert('RGBA')
            texture = stage / 'straight.png'
            straight.save(texture)
        options = {'canvasModule': str(canvas_module.resolve()),
                   'runtime': str(sources[spec['runtime']].resolve()),
                   'texture': str(texture.resolve()), 'atlas': str(sources[spec['atlas']].resolve()),
                   'skeleton': str(sources[spec['skeleton']].resolve()),
                   'clips': spec['export_clips'], 'fps': spec['fps'], 'size': spec['size'],
                   'supersample': 4, 'output': str(output.resolve())}
        config = stage / 'config.json'
        config.write_text(json.dumps(options))
        subprocess.run(['node', str(Path(__file__).with_name('spine_export.js')), str(config)],
                       check=True, timeout=180)
    data = json.loads(report.read_text())
    clip = next(c for c in data['clips'] if c['name'] == spec['animation'])
    for frame in clip['frames']:
        with Image.open(frame['file']) as image:
            yield image.convert('RGBA'), frame['duration_ms']


def decode(spec: dict, sources: dict[str, Path], work: Path, canvas_module: Path | None = None):
    kind = spec['kind']
    if kind == 'gif':
        with Image.open(sources[spec['source']]) as image:
            for index in range(image.n_frames):
                image.seek(index)  # Pillow composes disposal and partial rectangles.
                yield image.convert('RGBA'), int(image.info['duration'])
    elif kind == 'png_sequence':
        for source in spec['sources']:
            with Image.open(sources[source]) as image:
                yield image.convert('RGBA'), spec['duration_ms']
    elif kind == 'esheep':
        yield from esheep_frames(sources[spec['source']], spec)
    elif kind == 'vp9_alpha':
        yield from video_frames(sources[spec['source']], spec, work)
    elif kind == 'spine38':
        yield from spine_frames(spec, sources, work, canvas_module)
    else:
        raise ValueError(f'Unsupported source kind: {kind}')
