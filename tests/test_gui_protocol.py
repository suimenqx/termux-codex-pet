"""Protocol failure/recovery at real socket and descriptor boundaries."""
import json
import os
import socket
import struct
import tempfile
import time
import unittest
import array
import threading

from codex_pet.renderer.transport import Connection


class ProtocolTests(unittest.TestCase):
    def connection(self, ack=b'\0', **kwargs):
        main, peer = socket.socketpair()
        event, events = socket.socketpair()
        for stream in (main, peer, event, events):
            self.addCleanup(stream.close)
        peer.sendall(ack)
        connection = Connection.from_sockets(main, event, timeout=.05, **kwargs)
        self.addCleanup(connection.close)
        self.assertEqual(peer.recv(1), b'\1')
        return connection, peer, events

    def test_eof_ends_the_connection_instead_of_spinning(self):
        connection, peer, _ = self.connection()
        peer.shutdown(socket.SHUT_WR)
        with self.assertRaises(ConnectionError):
            connection.getversion()
        self.assertEqual(connection._main.fileno(), -1)

    def test_partial_and_invalid_replies_discard_the_connection(self):
        for data in (b'\0\0', (8).to_bytes(4, 'big') + b'{}',
                     (0).to_bytes(4, 'big'), (8_000_000).to_bytes(4, 'big'),
                     (1).to_bytes(4, 'big') + b'x'):
            with self.subTest(data=data):
                connection, peer, _ = self.connection()
                peer.sendall(data)
                with self.assertRaises((OSError, ValueError)):
                    connection.getversion()
                self.assertEqual(connection._event.fileno(), -1)

    def test_wrong_uid_and_protocol_are_rejected(self):
        with self.assertRaises(PermissionError):
            self.connection(expected_uid=os.getuid() + 1)
        with self.assertRaises(ConnectionError):
            self.connection(ack=b'\2')

    def test_slow_reply_cannot_restart_the_total_deadline(self):
        connection, peer, _ = self.connection()
        def drip():
            try:
                for byte in (4).to_bytes(4, 'big') + b'1234':
                    peer.sendall(bytes([byte]))
                    time.sleep(.025)
            except OSError:
                pass
        thread = threading.Thread(target=drip)
        thread.start()
        try:
            with self.assertRaises(TimeoutError):
                connection.getversion()
        finally:
            thread.join(1)

    def test_received_descriptor_is_owned_once_and_extra_fds_are_closed(self):
        for count in (0, 1, 2):
            with self.subTest(count=count), tempfile.TemporaryFile() as shared:
                connection, peer, _ = self.connection()
                shared.truncate(16)
                before = len(os.listdir('/proc/self/fd'))
                ancillary = ([(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                               array.array('i', [shared.fileno()] * count))] if count else [])
                peer.sendmsg([(1).to_bytes(4, 'big') + b'7'], ancillary)
                if count == 1:
                    bid, fd = connection.request_fd({'method': 'addBuffer'})
                    try:
                        self.assertEqual(bid, 7)
                        self.assertEqual(os.fstat(fd).st_size, 16)
                        self.assertFalse(os.get_inheritable(fd))
                    finally:
                        os.close(fd)
                    self.assertEqual(len(os.listdir('/proc/self/fd')), before)
                else:
                    with self.assertRaises(ConnectionError):
                        connection.request_fd({'method': 'addBuffer'})
                    self.assertEqual(len(os.listdir('/proc/self/fd')), before - 2)

    def test_native_repeated_descriptor_on_each_write_is_owned_once(self):
        with tempfile.TemporaryFile() as shared:
            shared.truncate(16)
            connection,peer,_=self.connection()
            before=len(os.listdir('/proc/self/fd'))
            for part in (b'\0',b'\0',b'\0',b'\1',b'7'):
                peer.sendmsg([part],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[shared.fileno()]))])
            bid,fd=connection.request_fd({'method':'addBuffer'})
            try:
                self.assertEqual((bid,os.fstat(fd).st_size),(7,16))
                self.assertEqual(len(os.listdir('/proc/self/fd')),before+1)
            finally:os.close(fd)
            self.assertEqual(len(os.listdir('/proc/self/fd')),before)

    def test_event_stream_eof_is_bounded_and_fresh_connection_works(self):
        connection, _, events = self.connection()
        events.close()
        with self.assertRaises(ConnectionError):
            connection.checkevent()
        fresh, peer, _ = self.connection()
        peer.sendall(b'\0\0\0\1' + b'7')
        self.assertEqual(fresh.getversion(), 7)


if __name__ == '__main__':
    unittest.main()
