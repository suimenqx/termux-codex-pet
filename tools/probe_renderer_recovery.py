#!/usr/bin/env python3
"""Inject one fence failure into a real native connection and observe worker fallback."""
from dataclasses import asdict
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codex_pet import gui  # noqa: E402
from codex_pet.renderer.policy import RendererPolicy  # noqa: E402
from codex_pet.renderer.transport import Connection  # noqa: E402
from tools.probe_production_renderer import resources  # noqa: E402


class FaultConnection(Connection):
    def __init__(self, fault):
        self.fault = fault
        self.versions = 0
        self.aid = None
        super().__init__()

    def send_read_msg(self, message):
        result = super().send_read_msg(message)
        if isinstance(message, dict) and message.get('method') == 'newActivity':
            self.aid = result
        return result

    def getversion(self):
        self.versions += 1
        if self.versions == 2:
            if self.fault == 'timeout':
                self.timeout = .15
                # Verified APK 7 has no overlay response for this method.
                # Replace one consumption reply with that real no-reply path.
                return self.send_read_msg({'method': 'getConfiguration', 'params': {'aid': self.aid}})
            self._main.shutdown(socket.SHUT_RD)
        return super().getversion()


def probe():
    results = []
    for fault in ('timeout', 'eof'):
        before = resources()
        connections = []
        ready = threading.Event()

        def connect():
            c = FaultConnection(fault) if not connections else Connection()
            connections.append(c)
            return c

        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'config.json'
            config.write_text('{"position":{"x":80,"y":120}}')
            policy = RendererPolicy(
                RendererPolicy.installed().binding_version, True)
            worker = gui.GuiWorker(config, lambda: {'appearance': 'akita', 'state': 'running', 'running_count': 2},
                                   lambda ok, error: ready.set() if ok else None, policy=policy)
            with patch.object(gui, 'Connection', side_effect=connect):
                worker.start()
                try:
                    if not ready.wait(15):
                        raise TimeoutError(
                            'Real worker did not recover on PNG')
                    snapshot = worker.renderer_status
                    if snapshot.transport != 'png' or not snapshot.fallback_reason or len(connections) != 2:
                        raise AssertionError(asdict(snapshot))
                    for _ in range(30):
                        worker.wake()
                    result = {'fault': fault, 'connections': len(connections), 'status': asdict(snapshot),
                              'before': before, 'recovered': resources()}
                finally:
                    worker.stop()
        result['after_stop'] = resources()
        results.append(result)
    return {'method': 'Production worker/binding and real APK; a single synthetic fence fault on the first native connection. Timeout substitutes the known overlay getConfiguration no-reply path; EOF shuts down the local read side. Only the connection factory is injected. The normal installed daemon is unchanged.',
            'limits': 'Local FD/map observations only. Native Android resource cleanup still needs independent observation.',
            'cases': results}


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: probe_renderer_recovery.py output.json')
    path = Path(sys.argv[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(probe(), indent=2) + '\n')
    print(path)
