"""Capability selection and diagnostics through the native wire boundary."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from gui_peer import GuiPeer
from codex_pet import gui
from codex_pet.renderer.policy import RendererPolicy
from codex_pet.renderer.protocol import RgbaFrame
from codex_pet.renderer.termux_gui import TermuxGuiRenderer, RebuildRenderer


class RendererPolicyTests(unittest.TestCase):
    def test_default_is_gated_and_unknown_capabilities_stay_png(self):
        for binding, plugin, size, approved, expected in (
            ('0.1.6', 7, (256, 256), False, 'png'),
            ('0.1.6', 7, (256, 256), True, 'shared'),
            ('0.1.6', 7, (64, 64), True, 'png'),
            ('0.1.6', 7, (384, 416), True, 'png'),
            ('0.1.7', 7, (256, 256), True, 'png'),
            ('0.1.6', 8, (256, 256), True, 'png'),
        ):
            with self.subTest(binding=binding, plugin=plugin, size=size, approved=approved):
                peer = GuiPeer(version=plugin)
                renderer = TermuxGuiRenderer(
                    peer.connection, policy=RendererPolicy(binding, approved))
                try:
                    renderer.present(
                        RgbaFrame(('frame', size), *size, bytes(size[0] * size[1] * 4)))
                    self.assertEqual(renderer.transport, expected)
                    self.assertEqual(renderer.plugin_version, plugin)
                    self.assertTrue(renderer.policy_reason)
                    peer.connection.getversion()
                    self.assertEqual(
                        any(m['method'] == 'addBuffer' for m in peer.messages), expected == 'shared')
                finally:
                    renderer.close()
                    peer.close()

    def test_strategy_change_retires_the_old_png_connection(self):
        peer = GuiPeer()
        renderer = TermuxGuiRenderer(
            peer.connection, policy=RendererPolicy('0.1.6', True))
        try:
            renderer.present(RgbaFrame(('robot',), 64, 64, bytes(64 * 64 * 4)))
            with self.assertRaises(RebuildRenderer):
                renderer.present(
                    RgbaFrame(('akita',), 256, 256, bytes(256 * 256 * 4)))
            self.assertEqual(peer.connection._main.fileno(), -1)
        finally:
            renderer.close()
            peer.close()

    def test_worker_status_retains_failure_after_recovery(self):
        peers = []
        ready = threading.Event()

        def connect():
            peer = GuiPeer(
                fail='fence_timeout' if not peers else '', timeout=.03)
            peers.append(peer)
            return peer.connection

        with tempfile.TemporaryDirectory() as temp:
            worker = gui.GuiWorker(Path(temp) / 'config.json', lambda: {'appearance': 'akita', 'state': 'idle'},
                                   lambda ok, error: ready.set() if ok else None,
                                   policy=RendererPolicy('0.1.6', True))
            with patch.object(gui, 'Connection', side_effect=connect):
                worker.start()
                try:
                    self.assertTrue(ready.wait(3))
                    status = worker.renderer_status
                    self.assertEqual(
                        (status.transport, status.binding_version, status.plugin_version), ('png', '0.1.6', 7))
                    self.assertIn('timed out', status.fallback_reason)
                    self.assertIn('timed out', status.last_connection_error)
                finally:
                    worker.stop()
            for peer in peers:
                peer.close()


if __name__ == '__main__':
    unittest.main()
