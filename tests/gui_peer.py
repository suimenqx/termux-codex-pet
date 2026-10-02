"""Local protocol peer using real sockets, shared files and native wire messages."""
import array
import json
import os
import socket
import tempfile
import threading
from codex_pet.renderer.transport import Connection


class GuiPeer:
    def __init__(self, fail='', timeout=.1, bad_capacity=False, version=7):
        main, self.peer = socket.socketpair()
        event, self.events = socket.socketpair()
        self.fail, self.bad_capacity, self.version = fail, bad_capacity, version
        self.messages = []
        self.blits = []
        self.buffers = []
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        self.connection = Connection.from_sockets(main, event, timeout=timeout)

    def _exact(self, n):
        data = b''
        while len(data) < n:
            part = self.peer.recv(n - len(data))
            if not part:
                raise EOFError
            data += part
        return data

    def _reply(self, value, fd=None):
        data = json.dumps(value).encode()
        wire = len(data).to_bytes(4, 'big') + data
        ancillary = [] if fd is None else [
            (socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', [fd]))]
        self.peer.sendmsg([wire], ancillary)

    def _serve(self):
        try:
            assert self._exact(1) == b'\1'
            self.peer.sendall(b'\0')
            while True:
                message = json.loads(self._exact(
                    int.from_bytes(self._exact(4), 'big')))
                self.messages.append(message)
                method = message['method']
                params = message.get('params', {})
                at_fence = method == 'getVersion' and bool(self.buffers)
                if method == self.fail or (at_fence and self.fail == 'fence_eof'):
                    break
                if at_fence and self.fail == 'fence_timeout':
                    continue
                if method == 'getVersion':
                    self._reply(self.version)
                elif method in ('newActivity', 'createLinearLayout', 'createImageView'):
                    self._reply(len(self.messages))
                elif method == 'getDimensions':
                    self._reply([192, 192])
                elif method == 'addBuffer':
                    shared = tempfile.TemporaryFile()
                    shared.truncate(
                        4 if self.bad_capacity else params['w'] * params['h'] * 4)
                    self.buffers.append(shared)
                    if self.fail == 'readonly':
                        fd = os.open('/proc/self/fd/' +
                                     str(shared.fileno()), os.O_RDONLY)
                        try:
                            self._reply(len(self.buffers), fd)
                        finally:
                            os.close(fd)
                    else:
                        self._reply(len(self.buffers), shared.fileno())
                elif method == 'blitBuffer':
                    shared = self.buffers[params['bid'] - 1]
                    shared.seek(0)
                    self.blits.append(shared.read())
        except (OSError, EOFError):
            pass
        finally:
            for shared in self.buffers:
                shared.close()
            self.peer.close()
            self.events.close()
            self.closed.set()

    def close(self):
        self.connection.close()
        self.thread.join(1)
        assert self.closed.is_set()
