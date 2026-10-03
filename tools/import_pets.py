#!/usr/bin/env python3
"""Convert pinned community recipes to independent local Pet Packs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.pet_import.pipeline import build_recipe  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='List recipes without downloading')
    parser.add_argument('--pet', action='append', help='Recipe ID; repeat to select several')
    parser.add_argument('--all', action='store_true', help='Build all maintained recipes')
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/codex-pet/import-sources')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--canvas-module', type=Path, help='Existing @napi-rs/canvas package directory')
    parser.add_argument('--setup-spine', action='store_true', help='Install pinned offline Canvas dependency in cache')
    args = parser.parse_args()
    recipes = {p.stem: p for p in sorted((ROOT / 'community_pets').glob('*.json'))}
    if args.list:
        for ident, path in recipes.items():
            print(f'{ident}: {json.loads(path.read_text())["name"]}')
        return
    if not args.output or (not args.pet and not args.all) or (args.pet and args.all):
        parser.error('Provide --output and exactly one of --all or --pet ID')
    selected = list(recipes) if args.all else list(dict.fromkeys(args.pet))
    if unknown := set(selected) - recipes.keys():
        parser.error(f'Unknown IDs: {", ".join(sorted(unknown))}')
    module = args.canvas_module
    if args.setup_spine:
        dependencies = args.cache / 'spine-deps'
        dependencies.mkdir(parents=True, exist_ok=True)
        for name in ('package.json', 'package-lock.json'):
            shutil.copyfile(ROOT / 'tools/pet_import/spine-deps' / name, dependencies / name)
        subprocess.run(['npm', 'ci', '--prefix', str(dependencies), '--ignore-scripts',
                        '--no-audit', '--no-fund'], check=True, timeout=180)
        module = dependencies / 'node_modules/@napi-rs/canvas'
    if module is None:
        candidate = args.cache / 'spine-deps/node_modules/@napi-rs/canvas'
        if candidate.exists():
            module = candidate
    for ident in selected:
        result = build_recipe(recipes[ident], args.cache, args.output, args.download, module)
        print(f'Built {result}; install with: codex-pet pet import {result}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f'Import failed: {error}', file=sys.stderr)
        sys.exit(1)
