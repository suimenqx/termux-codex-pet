"""Shared presentation and fresh PNG recovery at the real protocol/FD boundary."""
import os
import socket
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from gui_peer import GuiPeer
from codex_pet.renderer.protocol import RgbaFrame
from codex_pet.renderer.termux_gui import TermuxGuiRenderer
from codex_pet.image_codec import premultiply
from codex_pet import gui


class SharedRendererTests(unittest.TestCase):
    def test_event_eof_and_move_failure_also_disable_shared_until_restart(self):
        for fault in ('event_eof', 'move_failure'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temp:
                peers = []
                first_ready, recovered = threading.Event(), threading.Event()

                def connect():
                    peer = GuiPeer()
                    peers.append(peer)
                    return peer.connection

                def on_status(ok, error):
                    if ok:
                        (first_ready if len(peers) == 1 else recovered).set()

                # Static Robot ensures the failure is in event/move handling,
                # with no animation deadline accidentally testing present again.
                worker = gui.GuiWorker(Path(temp) / 'config.json',
                                       lambda: {'appearance': 'robot', 'state': 'idle'}, on_status, transport='shared')
                with patch.object(gui, 'Connection', side_effect=connect):
                    worker.start()
                    held_main = None
                    try:
                        self.assertTrue(first_ready.wait(3))
                        if fault == 'event_eof':
                            peers[0].events.shutdown(socket.SHUT_WR)
                        else:
                            # Keep the peer alive while invalidating the worker's
                            # write descriptor. Otherwise server EOF closes its
                            # event channel before both touches can be delivered.
                            held_main = peers[0].connection._main.dup()
                            peers[0].connection._main.close()
                            peers[0].emit('overlayTouch', {
                                          'action': 'down', 'x': 720, 'y': 440})
                            peers[0].emit('overlayTouch', {
                                          'action': 'move', 'x': 780, 'y': 500})
                        self.assertTrue(recovered.wait(3))
                        self.assertEqual(
                            worker.renderer_status.transport, 'png')
                        self.assertTrue(worker.renderer_status.fallback_reason)
                        self.assertEqual(len(peers), 2)
                        self.assertTrue(peers[1].image_received.wait(1))
                        self.assertFalse(
                            any(row['method'] == 'addBuffer' for row in peers[1].messages))
                        self.assertTrue(
                            any(row['method'] == 'setImage' for row in peers[1].messages))
                    finally:
                        worker.stop()
                        if held_main is not None:
                            held_main.close()
                        for peer in peers:
                            peer.close()

    def test_present_fences_staging_and_deduplicates_only_success(self):
        for size in ((64, 64), (256, 256), (384, 416)):
            before = len(os.listdir('/proc/self/fd'))
            peer = GuiPeer()
            renderer = TermuxGuiRenderer(peer.connection, transport='shared')
            try:
                width, height = size
                frame = RgbaFrame(('frame', size), width, height, bytes(
                    [100, 150, 200, 128]) * (width * height))
                renderer.present(frame)
                renderer.present(frame)
                self.assertEqual(
                    peer.blits, [premultiply(width, height, frame.pixels)])
                methods = [row['method'] for row in peer.messages]
                self.assertEqual(methods.count('addBuffer'), 1)
                self.assertEqual(methods.count('blitBuffer'), 1)
                self.assertLess(methods.index('blitBuffer'),
                                methods.index('refreshImageView'))
                self.assertEqual(methods[-1], 'getVersion')
            finally:
                renderer.close()
                renderer.close()
                peer.close()
            self.assertFalse(
                any(row['method'] == 'deleteBuffer' for row in peer.messages))
            self.assertEqual(len(os.listdir('/proc/self/fd')), before)

    def test_every_failed_shared_stage_closes_connection_and_mapping(self):
        for failure in ('addBuffer', 'blitBuffer', 'setBuffer', 'refreshImageView', 'fence_eof', 'fence_timeout', 'capacity', 'readonly'):
            with self.subTest(failure=failure):
                before = len(os.listdir('/proc/self/fd'))
                peer = GuiPeer(fail=failure, bad_capacity=failure ==
                               'capacity', timeout=.03)
                renderer = TermuxGuiRenderer(
                    peer.connection, transport='shared')
                try:
                    with self.assertRaises(Exception):
                        renderer.present(
                            RgbaFrame(('x',), 64, 64, bytes(64 * 64 * 4)))
                    self.assertIsNone(renderer.last_key)
                    self.assertEqual(peer.connection._main.fileno(), -1)
                finally:
                    renderer.close()
                    peer.close()
                self.assertEqual(len(os.listdir('/proc/self/fd')), before)

    def test_unknown_plugin_does_not_allocate_or_reuse_the_connection(self):
        peer = GuiPeer(version=8)
        renderer = TermuxGuiRenderer(peer.connection, transport='shared')
        try:
            with self.assertRaisesRegex(Exception, 'No verified'):
                renderer.present(
                    RgbaFrame(('future',), 64, 64, bytes(64 * 64 * 4)))
            self.assertEqual(peer.connection._main.fileno(), -1)
            self.assertFalse(
                any(row['method'] == 'addBuffer' for row in peer.messages))
        finally:
            renderer.close()
            peer.close()

    def test_resize_demands_a_new_connection(self):
        peer = GuiPeer()
        renderer = TermuxGuiRenderer(peer.connection, transport='shared')
        try:
            renderer.present(RgbaFrame(('small',), 64, 64, bytes(64 * 64 * 4)))
            with self.assertRaisesRegex(Exception, 'dimensions'):
                renderer.present(
                    RgbaFrame(('large',), 384, 416, bytes(384 * 416 * 4)))
        finally:
            renderer.close()
            peer.close()
        self.assertEqual(
            sum(row['method'] == 'addBuffer' for row in peer.messages), 1)

    def test_worker_remembers_shared_failure_and_recovers_on_fresh_png_connection(self):
        peers = []
        ready = threading.Event()

        def connect():
            peer = GuiPeer(
                fail='fence_timeout' if not peers else '', timeout=.05)
            peers.append(peer)
            return peer.connection
        with tempfile.TemporaryDirectory() as temp:
            worker = gui.GuiWorker(Path(temp) / 'config.json', lambda: {'appearance': 'akita', 'state': 'running', 'running_count': 2},
                                   lambda ok, error: ready.set() if ok else None, transport='shared')
            with patch.object(gui, 'Connection', side_effect=connect):
                worker.start()
                try:
                    self.assertTrue(ready.wait(3))
                    for _ in range(30):
                        worker.wake()
                    self.assertEqual(len(peers), 2)
                    self.assertTrue(peers[0].closed.is_set())
                    self.assertTrue(peers[1].image_received.wait(1))
                    self.assertTrue(
                        any(row['method'] == 'setImage' for row in peers[1].messages))
                    self.assertFalse(
                        any(row['method'] == 'addBuffer' for row in peers[1].messages))
                finally:
                    worker.stop()
            for peer in peers:
                peer.close()


if __name__ == '__main__':
    unittest.main()
