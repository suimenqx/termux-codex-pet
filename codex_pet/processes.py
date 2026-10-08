"""Codex producer/client identities and exit descriptors, independent of native UI."""
from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import select
from typing import Any

from .adapters.codex import BOOT_ID, SHARED_INSTANCE_PREFIX


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start_ticks: int
    boot_id: str

    @property
    def instance_id(self) -> str:
        return hashlib.sha256(f'{self.boot_id}/{self.pid}/{self.start_ticks}'.encode()).hexdigest()

    def fields(self, *, shared: bool = False) -> dict[str, Any]:
        # Encode the role in the opaque token so format-2 checkpoints remain
        # readable by the retained previous release during rollback.
        value = {'instance_id': (SHARED_INSTANCE_PREFIX if shared else '') + self.instance_id,
                 'producer_pid': self.pid, 'producer_start_ticks': self.start_ticks,
                 'producer_boot_id': self.boot_id}
        if shared:
            value['instance_tracking'] = 'shared'
        return value


def process_stat(pid: int) -> tuple[int, int, str]:
    value = (Path('/proc') / str(pid) / 'stat').read_text()
    fields = value[value.rfind(')') + 2:].split()
    return int(fields[1]), int(fields[19]), fields[0]


def discover_owner() -> dict[str, Any]:
    """Identify a shared managed server, or the CLI owning a local server child."""
    pid, saw_server = os.getppid(), False
    seen = set()
    for _ in range(32):
        if pid <= 1 or pid in seen:
            break
        seen.add(pid)
        try:
            parent, ticks, state = process_stat(pid)
            proc = Path('/proc') / str(pid)
            executable = Path(os.readlink(proc / 'exe')).name.removesuffix(' (deleted)')
            if executable in ('codex', 'codex.bin') and state not in ('Z', 'X'):
                args = (proc / 'cmdline').read_bytes().split(b'\0')
                if len(args) > 1 and args[1] == b'app-server':
                    # A managed server owns execution independently of any TUI.
                    # Use its identity even before its launcher is reparented.
                    if b'--managed-daemon' in args[2:] and BOOT_ID:
                        return ProcessIdentity(pid, ticks, BOOT_ID).fields(shared=True)
                    saw_server = True
                else:
                    return ProcessIdentity(pid, ticks, BOOT_ID).fields() if BOOT_ID else {}
            pid = parent
        except (OSError, ValueError, IndexError):
            break
    # An orphaned app-server must not become a fresh CLI instance after its
    # client died. Explicit/manual senders without Codex ancestry stay legacy.
    return {'instance_tracking': 'orphan'} if saw_server else {}


def discover_clients() -> tuple[dict[str, ProcessIdentity], str]:
    """Find this user's native CLI clients; shared servers are not clients.

    Discovery runs on lifecycle/IPC wakes, never on a polling timer. Once
    discovered, clients use the same verified kernel exit descriptors as
    producers. Arguments are inspected transiently and never persisted.
    """
    clients: dict[str, ProcessIdentity] = {}
    error = ''
    if not BOOT_ID:
        return clients, 'Codex client boot identity cannot be verified'
    try:
        for proc in Path('/proc').iterdir():
            if not proc.name.isdecimal():
                continue
            own_process = False
            try:
                if proc.stat().st_uid != os.getuid():
                    continue
                own_process = True
                pid = int(proc.name)
                _, ticks, state = process_stat(pid)
                if state in ('Z', 'X'):
                    continue
                executable = Path(os.readlink(proc / 'exe')).name.removesuffix(' (deleted)')
                if executable not in ('codex', 'codex.bin'):
                    continue
                args = (proc / 'cmdline').read_bytes().split(b'\0')
                if len(args) > 1 and args[1] in (b'app-server', b'mcp-server'):
                    continue
                identity = ProcessIdentity(pid, ticks, BOOT_ID)
                clients[identity.instance_id] = identity
            except (FileNotFoundError, ProcessLookupError):
                pass
            except (OSError, ValueError, IndexError):
                if own_process:
                    error = 'Codex client identity cannot be verified'
    except OSError:
        error = 'Codex client discovery unavailable'
    return clients, error


def process_alive(identity: ProcessIdentity) -> bool | None:
    if identity.boot_id != BOOT_ID:
        return False
    try:
        _, ticks, state = process_stat(identity.pid)
        return ticks == identity.start_ticks and state not in ('Z', 'X')
    except (FileNotFoundError, ProcessLookupError):
        return False
    except (OSError, ValueError, IndexError):
        return None


def open_pidfd(pid: int) -> int:
    call = getattr(os, 'pidfd_open', None)
    if call is not None:
        return call(pid, 0)
    # Termux's Python can omit os.pidfd_open although Android libc exposes it.
    # This is the typed public libc function, never a guessed syscall number.
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    call = getattr(libc, 'pidfd_open', None)
    if call is None:
        raise OSError(errno.ENOSYS, 'pidfd_open is unavailable')
    call.argtypes = [ctypes.c_int, ctypes.c_uint]
    call.restype = ctypes.c_int
    fd = call(pid, 0)
    if fd < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    os.set_inheritable(fd, False)
    return fd


class ProcessWatcher:
    def __init__(self) -> None:
        self.watches: dict[str, tuple[ProcessIdentity, int]] = {}

    @property
    def descriptors(self) -> list[int]:
        return [fd for _, fd in self.watches.values()]

    def sync(self, owners: dict[str, ProcessIdentity]) -> tuple[dict[str, ProcessIdentity], dict[str, str]]:
        closed: dict[str, ProcessIdentity] = {}
        errors: dict[str, str] = {}
        for owner in list(self.watches):
            if owner not in owners or owners[owner] != self.watches[owner][0]:
                os.close(self.watches.pop(owner)[1])
        for owner, identity in owners.items():
            if owner in self.watches:
                fd = self.watches[owner][1]
                if select.select([fd], [], [], 0)[0]:
                    closed[owner] = identity
                continue
            alive = process_alive(identity)
            if alive is False:
                closed[owner] = identity
                continue
            if alive is None:
                errors[owner] = 'Codex producer identity cannot be verified'
                continue
            try:
                fd = open_pidfd(identity.pid)
            except OSError as exc:
                if process_alive(identity) is False:
                    closed[owner] = identity
                else:
                    errors[owner] = f'Codex producer exit monitoring unavailable: {exc}'[:180]
                continue
            # Fence PID recycling between reading /proc and acquiring the FD.
            alive = process_alive(identity)
            if alive is not True:
                os.close(fd)
                if alive is False:
                    closed[owner] = identity
                else:
                    errors[owner] = 'Codex producer identity cannot be verified'
                continue
            self.watches[owner] = identity, fd
            if select.select([fd], [], [], 0)[0]:
                closed[owner] = identity
        for owner in closed:
            if owner in self.watches:
                os.close(self.watches.pop(owner)[1])
        return closed, errors

    def close(self) -> None:
        for _, fd in self.watches.values():
            os.close(fd)
        self.watches.clear()
