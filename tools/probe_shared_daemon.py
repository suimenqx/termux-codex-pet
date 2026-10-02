#!/usr/bin/env python3
"""Temporarily run the installed production daemon with gated shared capability.

This opt-in acceptance tool uses the real one-daemon lock and user configuration.
It restarts the normal installed daemon in finally; it does not change the
release's default policy or add a user-facing mode.
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=300)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 1800:
        parser.error('seconds must be between 30 and 1800')
    home = Path.home()
    release = (home / '.local/share/codex-pet/current').resolve(strict=True)
    cli = str(home / '.local/bin/codex-pet')
    log_path = home / '.cache/codex-pet/shared-acceptance.log'
    env = {**os.environ, 'PYTHONPATH': str(release)}
    sys.path.insert(0, str(release))
    from codex_pet.runtime import request
    child = None

    def interrupt(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    subprocess.run([cli, 'stop'], check=True)
    try:
        with log_path.open('a') as log:
            child = subprocess.Popen([sys.executable, '-c',
                'from codex_pet.daemon import main; from codex_pet.renderer.policy import RendererPolicy; '
                'main(renderer_policy=RendererPolicy(RendererPolicy.installed().binding_version, True))'],
                cwd=release, env=env, stdout=log, stderr=log, start_new_session=True)
        startup_deadline = time.monotonic() + 10
        while True:
            if child.poll() is not None:
                raise RuntimeError('Acceptance daemon exited during startup')
            try:
                status = request({'action': 'status'}, .2)
            except (OSError, ValueError):
                status = {}
            if status.get('gui_ready') and status.get('pid') == child.pid:
                if status['renderer']['transport'] != 'shared':
                    raise RuntimeError('The current capability did not select shared')
                break
            if time.monotonic() >= startup_deadline:
                raise TimeoutError('Acceptance daemon did not become ready')
            time.sleep(.1)
        subprocess.run([cli, 'status'], check=True)
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError('Controlled daemon exited before acceptance completed')
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    finally:
        subprocess.run([cli, 'stop'], check=False)
        if child is not None:
            try:
                child.wait(timeout=12)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=5)
        subprocess.run([cli, 'start'], check=True)


if __name__ == '__main__':
    main()
