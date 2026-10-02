"""Rebuild this rejected candidate's review, independent of live animation state."""

from pathlib import Path
import base64
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.historical_art import _decode_rgba_png
from tools.audit_animation import (
    PAW_COLORS, RenderedFrame, _contact_sheet, _draw_paw_marker,
    _resize_rgba, _track_transitions,
)

PACKAGE = Path(__file__).resolve().parent


def build() -> None:
    candidate = json.loads((PACKAGE / 'candidate.json').read_text())
    previous = json.loads((PACKAGE / 'previous-running.json').read_text())
    order = [0, 8, 1, 2, 3, 4, 9, 5, 6, 7]
    before = [dict(previous['frames'][i],
                   file='originals/frames/running/' + previous['frames'][i]['file'],
                   physical=i) for i in order]
    after = [dict(item, physical=i) for i, item in enumerate(candidate['frames'])]
    clips = [before, after]
    report = {
        'production_accepted': False,
        'coordinate_frame': 'fixed canvas, 4 source pixels per 64dp-view dp; no hip subtraction',
        'scope': 'painted-paw displacement/exposure, not anatomical velocity or contact proof',
        'annotation_uncertainty': candidate['annotation_uncertainty'],
        'clips': [],
    }
    review = PACKAGE / 'review'
    review.mkdir(exist_ok=True)
    for label, rows in zip(['previous', 'candidate'], clips):
        diagnostics = {'label': label, 'cycle_seconds': round(sum(r['seconds'] for r in rows), 3),
                       'paws': {}}
        for paw in PAW_COLORS:
            diagnostics['paws'][paw] = _track_transitions(
                [r['paw_centers'][paw] for r in rows], [r['seconds'] for r in rows],
                [r['physical'] for r in rows], 4,
            )
        report['clips'].append(diagnostics)
        for size in [64, 192]:
            frames = []
            marked = []
            for step, row in enumerate(rows * 2):
                _, _, source = _decode_rgba_png((PACKAGE / row['file']).read_bytes())
                pixels = _resize_rgba(source, size)
                frames.append(RenderedFrame(step, row['physical'], row['seconds'], pixels))
                points = bytearray(pixels)
                for paw, point in row['paw_centers'].items():
                    if point is not None:
                        _draw_paw_marker(points, size, round(point[0] * size / 256),
                                         round(point[1] * size / 256), PAW_COLORS[paw], 2)
                marked.append(RenderedFrame(step, row['physical'], row['seconds'], bytes(points)))
            # Empty state deliberately disables the live production landmark mapping.
            (review / f'{label}-{size}.png').write_bytes(_contact_sheet(tuple(frames), size, ''))
            (review / f'{label}-{size}-markers.png').write_bytes(_contact_sheet(tuple(marked), size, ''))
    (review / 'spacing.json').write_text(json.dumps(report, indent=2) + '\n')
    embedded = []
    for rows in clips:
        embedded.append([dict(seconds=r['seconds'], physical=r['physical'],
                              src='data:image/png;base64,' + base64.b64encode(
                                  (PACKAGE / r['file']).read_bytes()).decode()) for r in rows])
    template = (PACKAGE / 'comparison-template.html').read_text()
    (PACKAGE / 'comparison.html').write_text(template.replace('CLIPS_DATA', json.dumps(embedded)))


if __name__ == '__main__':
    build()
