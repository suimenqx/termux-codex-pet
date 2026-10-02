#!/usr/bin/env python3
"""Controlled production renderer comparison; briefly creates a second overlay."""
from __future__ import annotations

import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codex_pet.frames import FrameSource, FrameComposer  # noqa: E402
from codex_pet.frame_cache import FrameCache  # noqa: E402
from codex_pet.pet_runtime import PetRuntime, PetVisual  # noqa: E402
from codex_pet.renderer.protocol import RgbaFrame  # noqa: E402
from codex_pet.renderer.termux_gui import TermuxGuiRenderer  # noqa: E402
from codex_pet.renderer.transport import Connection  # noqa: E402


def resources():
    return {
        'fds': len(os.listdir('/proc/self/fd')),
        'ashmem_maps': sum('/dev/ashmem' in line for line in Path('/proc/self/maps').read_text().splitlines()),
        'rss_kib': next(int(line.split()[1]) for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:')),
    }


class ObservedConnection(Connection):
    """Time actual protocol operations without changing production behavior."""

    def __init__(self):
        self.send_ms = self.fence_ms = 0.0
        self.methods = []
        super().__init__()

    def send_msg(self, message):
        started = time.perf_counter_ns()
        try:
            self.methods.append(message.get('method') if isinstance(
                message, dict) else json.loads(message)['method'])
            return super().send_msg(message)
        finally:
            self.send_ms += (time.perf_counter_ns() - started) / 1e6

    def getversion(self):
        started = time.perf_counter_ns()
        try:
            return super().getversion()
        finally:
            self.fence_ms += (time.perf_counter_ns() - started) / 1e6


def run_case(size, transport, samples, interval):
    before = resources()
    cache = FrameCache()
    source, composer = FrameSource(cache), FrameComposer(cache)
    started = time.perf_counter()
    c = ObservedConnection()
    renderer = None
    rows = []
    cpu = time.process_time()
    try:
        renderer = TermuxGuiRenderer(
            c, (80, 120), cache=cache, transport=transport)
        plugin = c.getversion()
        setup_ms = (time.perf_counter() - started) * 1000
        pet = 'robot' if size == (64, 64) else 'akita'
        deadline = time.monotonic()
        for index in range(samples + 18):
            # First idle and first Running are reported separately; subsequent
            # Running exposures use exactly the same timeline/deadlines.
            state = 'idle' if index == 0 else 'running'
            prepared = time.perf_counter_ns()
            runtime = PetRuntime(PetVisual(pet, state, 2), 0)
            runtime.tick(max(0, index - 1) * interval)
            request = runtime.current()
            frame = composer.compose(source.frame(
                pet, request.revision, request.reference), request.count)
            if size == (384, 416):
                # Place the unchanged Akita pixels on a larger transparent
                # test canvas. This is a size/lifecycle probe, not new artwork.
                pixels = bytearray(size[0] * size[1] * 4)
                for y in range(frame.height):
                    start = ((y + 80) * size[0] + 64) * 4
                    pixels[start:start + frame.width * 4] = frame.pixels[y *
                                                                         frame.width * 4:(y + 1) * frame.width * 4]
                frame = RgbaFrame(('padded', frame.key), *size, bytes(pixels))
            prepare_ms = (time.perf_counter_ns() - prepared) / 1e6
            send, fence = c.send_ms, c.fence_ms
            submitted = time.perf_counter_ns()
            changed = renderer.last_key != frame.key
            renderer.present(frame)
            if transport == 'png' and changed:
                # Same dispatch-consumption boundary for comparison.
                c.getversion()
            total = (time.perf_counter_ns() - submitted) / 1e6
            row = {'prepare_ms': prepare_ms,
                   'present_total_ms': total,
                   'send_ms': c.send_ms - send,
                   'fence_ms': c.fence_ms - fence,
                   'adapter_other_ms': total - (c.send_ms - send) - (c.fence_ms - fence),
                   'changed': changed}
            if index < 2 or index >= 18:
                rows.append(row)
            renderer.move(80 + (index % 4) * 2, 120)
            deadline += interval
            time.sleep(max(0, deadline - time.monotonic()))
        live = resources()
        cpu_seconds = time.process_time() - cpu
        result = {'canvas': size, 'transport': transport, 'plugin_protocol_version': plugin,
                  'setup_ms': setup_ms, 'cold_idle': rows[0], 'first_running': rows[1],
                  'warm_median': {key: statistics.median(row[key] for row in rows[2:] if row['changed']) for key in rows[0] if key != 'changed'},
                  'deduplicated_samples': sum(not row['changed'] for row in rows[2:]),
                  'samples': rows, 'python_cpu_seconds': cpu_seconds,
                  'before': before, 'live': live,
                  'blits': c.methods.count('blitBuffer'), 'png_sends': c.methods.count('setImage')}
    finally:
        if renderer is not None:
            renderer.close()
            renderer.close()
        c.close()
        cache.clear()
    result['after_close'] = resources()
    return result


def probe(rounds=2, samples=20, interval=.08):
    results = []
    for round_index in range(rounds):
        for size in ((64, 64), (256, 256), (384, 416)):
            order = ('png', 'shared') if round_index % 2 == 0 else (
                'shared', 'png')
            for transport in order:
                print(f'round={round_index + 1} canvas={size[0]}x{size[1]} transport={transport}', flush=True)
                results.append(run_case(size, transport, samples, interval))
    return {'binding': version('termuxgui'), 'rounds': rounds, 'interval_seconds': interval,
            'method': 'Serial, alternating order; same production frames/deadlines, fresh connection/cache per case; two initial exposures then 16 warmup exposures then timed samples. Warm medians exclude unchanged frames for both transports. PNG adds getVersion only for changed frames for comparable consumption. OS disk cache not flushed. Running production daemon remains active.',
            'limits': 'Python RSS/FD/maps only; native Android window/bitmap/FD evidence must be recorded separately. No screen-presentation, power or total-system CPU claim. Adapter-other includes encoding/premultiplication and bookkeeping.',
            'cases': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--samples', type=int, default=20)
    args = parser.parse_args()
    if args.rounds < 1 or args.samples < 2:
        parser.error('rounds >= 1 and samples >= 2 required')
    result = probe(args.rounds, args.samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(args.output)
