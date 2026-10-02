"""Keep the opt-in device probe finite on the binding's known EOF failure."""
import socket
import unittest

import termuxgui.msg

from tools.probe_termux_gui import EOFGuard, premultiply, summary


class RendererProbeTests(unittest.TestCase):
    def test_eof_during_header_fails_instead_of_spinning(self):
        left, right = socket.socketpair()
        with left:
            right.close()
            with self.assertRaises(ConnectionError):
                termuxgui.msg.read_msg(EOFGuard(left))

    def test_eof_during_partial_body_fails(self):
        left, right = socket.socketpair()
        with left:
            with right:
                right.sendall((20).to_bytes(4, "big") + b"{")
            with self.assertRaises(ConnectionError):
                termuxgui.msg.read_msg(EOFGuard(left))

    def test_eof_during_fd_body_fails(self):
        left, right = socket.socketpair()
        with left:
            with right:
                right.sendall((20).to_bytes(4, "big"))
            with self.assertRaises(ConnectionError):
                termuxgui.msg.read_msg_fd(EOFGuard(left))

    def test_guard_preserves_successful_message(self):
        left, right = socket.socketpair()
        with left, right:
            right.sendall((1).to_bytes(4, "big") + b"7")
            self.assertEqual(termuxgui.msg.read_msg(EOFGuard(left)), 7)

    def test_premultiply_keeps_alpha_and_rounds_channels(self):
        self.assertEqual(
            premultiply(bytes([255, 128, 1, 128, 255, 20, 30, 0, 1, 2, 3, 255])),
            bytes([128, 64, 1, 128, 0, 0, 0, 0, 1, 2, 3, 255]),
        )

    def test_summary_reports_nearest_rank_percentile(self):
        result = summary(list(range(1, 101)))
        self.assertEqual(result["median_ms"], 50.5)
        self.assertEqual(result["p95_ms"], 95)


if __name__ == "__main__":
    unittest.main()
