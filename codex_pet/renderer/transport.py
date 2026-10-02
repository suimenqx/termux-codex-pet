"""Bounded Termux:GUI JSON protocol, including connection establishment.

The installed binding's constructors/readers cannot safely handle EOF. Views
still use its API, but all transport ownership and deadlines live here.
"""
from __future__ import annotations

import array
import json
import os
import secrets
import select
import socket
import struct
import subprocess
import threading
import time
from typing import Any

from termuxgui.event import Event

MAX_REPLY_BYTES = 4 * 1024 * 1024
MAX_COMMAND_BYTES = 96 * 1024 * 1024


def _budget(stream: socket.socket, deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Termux:GUI operation deadline exceeded')
    stream.settimeout(remaining)


class Connection:
    def __init__(self, timeout: float = 4.0) -> None:
        self.timeout = timeout
        self._lock = threading.RLock()
        self._event_lock = threading.RLock()
        deadline = time.monotonic() + timeout
        for index, command in enumerate(('termux-am', 'am')):
            # Both launch variants share one total budget, including broadcast.
            attempt = deadline if index else time.monotonic() + max(0, deadline - time.monotonic()) / 2
            main_address, event_address = secrets.token_hex(24), secrets.token_hex(24)
            main = event = None
            try:
                with socket.socket(socket.AF_UNIX) as main_listener, socket.socket(socket.AF_UNIX) as event_listener:
                    main_listener.bind('\0' + main_address)
                    event_listener.bind('\0' + event_address)
                    main_listener.listen(1)
                    event_listener.listen(1)
                    remaining = attempt - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Termux:GUI startup deadline exceeded')
                    subprocess.run([command, 'broadcast', '-n', 'com.termux.gui/.GUIReceiver',
                                    '--es', 'mainSocket', main_address, '--es', 'eventSocket', event_address],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=remaining, check=True)
                    _budget(main_listener, attempt)
                    main, _ = main_listener.accept()
                    _budget(event_listener, attempt)
                    event, _ = event_listener.accept()
                    self._main, self._event = main, event
                    self._negotiate(attempt, os.getuid())
                    return
            except BaseException as exc:
                if main is not None:
                    main.close()
                if event is not None:
                    event.close()
                if (index or not isinstance(exc, (OSError, subprocess.SubprocessError))
                        or time.monotonic() >= deadline):
                    raise
        raise ConnectionError('Could not connect to Termux:GUI')

    @classmethod
    def from_sockets(cls, main: socket.socket, event: socket.socket,
                     timeout: float = 4.0, expected_uid: int | None = None) -> Connection:
        """Adopt connected sockets and perform the same verified handshake."""
        self = cls.__new__(cls)
        self.timeout = timeout
        self._lock = threading.RLock()
        self._event_lock = threading.RLock()
        self._main, self._event = main, event
        try:
            self._negotiate(time.monotonic() + timeout,
                            os.getuid() if expected_uid is None else expected_uid)
        except BaseException:
            self.close()
            raise
        return self

    def _negotiate(self, deadline: float, uid: int) -> None:
        for stream in (self._main, self._event):
            peer_uid = struct.unpack('3i', stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
            if peer_uid != uid:
                raise PermissionError('Termux:GUI peer has a different UID')
        _budget(self._main, deadline)
        self._main.sendall(b'\1')
        if self._read_exact(self._main, 1, deadline) != b'\0':
            raise ConnectionError('Invalid Termux:GUI protocol negotiation')

    def _read_exact(self, stream: socket.socket, length: int, deadline: float,
                    fds: list[int] | None = None) -> bytes:
        data = bytearray()
        while len(data) < length:
            _budget(stream, deadline)
            if fds is None:
                part = stream.recv(min(length - len(data), 65536))
            else:
                part, ancillary, flags, _ = stream.recvmsg(
                    min(length - len(data), 65536), socket.CMSG_SPACE(16 * array.array('i').itemsize))
                for level, kind, payload in ancillary:
                    if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                        values = array.array('i')
                        values.frombytes(payload[:len(payload) - len(payload) % values.itemsize])
                        fds.extend(values)
                if flags & socket.MSG_CTRUNC:
                    raise ConnectionError('Truncated Termux:GUI descriptors')
            if not part:
                raise ConnectionError('Termux:GUI closed the stream')
            data.extend(part)
        return bytes(data)

    def _read(self, stream: socket.socket, deadline: float, fds: list[int] | None = None) -> Any:
        length = int.from_bytes(self._read_exact(stream, 4, deadline, fds), 'big')
        if not 0 < length <= MAX_REPLY_BYTES:
            raise ValueError('Invalid Termux:GUI reply length')
        return json.loads(self._read_exact(stream, length, deadline, fds))

    def _send(self, message: str | dict, deadline: float) -> None:
        payload = (json.dumps(message) if isinstance(message, dict) else message).encode('utf-8')
        if not 0 < len(payload) <= MAX_COMMAND_BYTES:
            raise ValueError('Invalid Termux:GUI command length')
        _budget(self._main, deadline)
        self._main.sendall(len(payload).to_bytes(4, 'big') + payload)

    def send_msg(self, message: str | dict) -> None:
        with self._lock:
            try:
                self._send(message, time.monotonic() + self.timeout)
            except BaseException:
                self.close()
                raise

    def send_read_msg(self, message: str | dict) -> Any:
        with self._lock:
            deadline = time.monotonic() + self.timeout
            try:
                self._send(message, deadline)
                return self._read(self._main, deadline)
            except BaseException:
                self.close()
                raise

    def request_fd(self, message: dict) -> tuple[int, int]:
        """Return one validated descriptor; the caller then owns it."""
        descriptors: list[int] = []
        with self._lock:
            try:
                deadline = time.monotonic() + self.timeout
                self._send(message, deadline)
                value = self._read(self._main, deadline, descriptors)
                if type(value) is not int or value < 0 or len(descriptors) != 1:
                    raise ConnectionError('Invalid buffer ID or descriptor count')
                os.fstat(descriptors[0])
                os.set_inheritable(descriptors[0], False)
                return value, descriptors.pop()
            except BaseException:
                self.close()
                raise
            finally:
                for fd in descriptors:
                    os.close(fd)

    def checkevent(self) -> Event | None:
        with self._event_lock:
            try:
                if not select.select([self._event], [], [], 0)[0]:
                    return None
                return Event(self._read(self._event, time.monotonic() + self.timeout))
            except BaseException:
                self.close()
                raise

    def getversion(self) -> int:
        value = self.send_read_msg({'method': 'getVersion', 'params': {}})
        if type(value) is not int or value < 0:
            self.close()
            raise ValueError('Invalid Termux:GUI plugin version')
        return value

    def close(self) -> None:
        for stream in (self._main, self._event):
            stream.close()

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()
