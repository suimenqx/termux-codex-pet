"""Install an immutable runtime copy independent of the editable checkout."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Iterator
from uuid import uuid4

from . import hooks_config

APP_RELATIVE = Path(".local/share/codex-pet")
RELEASES = "releases"
CURRENT = "current"
PREVIOUS = "previous"
RELEASE_MARKER = ".codex-pet-release"
ENTRYPOINTS = ("codex-pet", "codex-pet-event")
ENTRYPOINT_MARKER = "# CODEX_PET_MANAGED_ENTRYPOINT="
SMOKE_SESSION = "install-smoke"


def _app_dir(home: Path) -> Path:
    return home / APP_RELATIVE


def _link_target(app_dir: Path, name: str) -> str | None:
    link = app_dir / name
    if link.is_symlink():
        return os.readlink(link)
    if link.exists():
        raise FileExistsError(f"Cannot replace non-symlink runtime path: {link}")
    return None


def _replace_link(app_dir: Path, name: str, target: str) -> None:
    link = app_dir / name
    if link.exists() and not link.is_symlink():
        raise FileExistsError(f"Cannot replace non-symlink runtime path: {link}")
    temporary = app_dir / f".{name}.{uuid4().hex}.tmp"
    try:
        temporary.symlink_to(target)
        os.replace(temporary, link)
    finally:
        temporary.unlink(missing_ok=True)


def _copy_entrypoint_backup(source: Path, backup: Path) -> None:
    backup.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if source.is_symlink():
        backup.symlink_to(os.readlink(source))
    else:
        shutil.copy2(source, backup)


def _is_managed_entrypoint(path: Path, name: str, source: Path) -> bool:
    if path.is_symlink():
        raw_target = Path(os.readlink(path))
        if not raw_target.is_absolute():
            raw_target = path.parent / raw_target
        return raw_target.resolve(strict=False) == (source / "bin" / name).resolve(strict=False)
    if not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as entrypoint:
            return any(
                line.rstrip("\n") == f"{ENTRYPOINT_MARKER}{name}"
                for _, line in zip(range(8), entrypoint)
            )
    except OSError:
        return False


def _entrypoint_text(name: str) -> str:
    return (
        "#!/data/data/com.termux/files/usr/bin/bash\n"
        f"{ENTRYPOINT_MARKER}{name}\n"
        "set -euo pipefail\n"
        f'exec python "$HOME/.local/share/codex-pet/current/bin/{name}" "$@"\n'
    )


def _install_entrypoints(source: Path, home: Path) -> None:
    local_bin = home / ".local" / "bin"
    backups = home / ".config" / "codex-pet" / "cli-backups"
    local_bin.mkdir(mode=0o700, parents=True, exist_ok=True)

    for name in ENTRYPOINTS:
        target = local_bin / name
        if target.is_dir() and not target.is_symlink():
            raise IsADirectoryError(f"Cannot install over directory: {target}")

    for name in ENTRYPOINTS:
        target = local_bin / name
        backup = backups / name
        if (target.exists() or target.is_symlink()) and not _is_managed_entrypoint(target, name, source):
            if not backup.exists() and not backup.is_symlink():
                _copy_entrypoint_backup(target, backup)

        temporary = local_bin / f".{name}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(_entrypoint_text(name), encoding="utf-8")
            temporary.chmod(0o700)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def _copy_runtime(source: Path, staging: Path) -> None:
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(source / "codex_pet", staging / "codex_pet", ignore=ignored)
    shutil.copytree(source / "bin", staging / "bin", ignore=ignored)
    (staging / RELEASE_MARKER).write_text("codex-pet\n", encoding="utf-8")

    for path in (staging, *staging.rglob("*")):
        if path.is_dir():
            path.chmod(0o700)
        elif path.is_file():
            mode = stat.S_IMODE(path.stat().st_mode)
            path.chmod(0o700 if mode & stat.S_IXUSR else 0o600)


def deploy(source: Path, home: Path | None = None) -> Path:
    """Copy the runtime to a private release and atomically activate it."""
    source = source.resolve()
    home = (home or Path.home()).resolve()
    if not (source / "codex_pet").is_dir() or not (source / "bin").is_dir():
        raise FileNotFoundError(f"Not a Codex Pet checkout: {source}")
    for name in ENTRYPOINTS:
        if not (source / "bin" / name).is_file():
            raise FileNotFoundError(f"Missing runtime entrypoint: {source / 'bin' / name}")

    app_dir = _app_dir(home)
    if app_dir.is_symlink():
        raise FileExistsError(f"Refusing to install through symlink: {app_dir}")
    app_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    releases_dir = app_dir / RELEASES
    releases_dir.mkdir(mode=0o700, exist_ok=True)
    old_current = _link_target(app_dir, CURRENT)
    _link_target(app_dir, PREVIOUS)

    release_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    release_dir = releases_dir / release_id
    staging = Path(tempfile.mkdtemp(prefix=".stage-", dir=releases_dir))
    try:
        _copy_runtime(source, staging)
        os.replace(staging, release_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    try:
        _install_entrypoints(source, home)
        if old_current is not None:
            _replace_link(app_dir, PREVIOUS, old_current)
        _replace_link(app_dir, CURRENT, f"{RELEASES}/{release_id}")
    except BaseException:
        raise
    return release_dir


def _managed_release(app_dir: Path, target: str | None) -> Path | None:
    if target is None:
        return None
    candidate = (app_dir / target).resolve(strict=False)
    releases_dir = (app_dir / RELEASES).resolve(strict=False)
    if candidate.parent != releases_dir or not candidate.is_dir():
        return None
    marker = candidate / RELEASE_MARKER
    if not marker.is_file() or marker.read_text(encoding="utf-8") != "codex-pet\n":
        return None
    return candidate


def rollback(home: Path | None = None) -> Path:
    """Swap current and previous managed releases."""
    home = (home or Path.home()).resolve()
    app_dir = _app_dir(home)
    current_target = _link_target(app_dir, CURRENT)
    previous_target = _link_target(app_dir, PREVIOUS)
    previous_release = _managed_release(app_dir, previous_target)
    if current_target is None or previous_release is None:
        raise FileNotFoundError("No previous Codex Pet runtime release is available")
    if _managed_release(app_dir, current_target) is None:
        raise RuntimeError("Current Codex Pet runtime link is not managed")
    _replace_link(app_dir, CURRENT, previous_target)
    _replace_link(app_dir, PREVIOUS, current_target)
    return previous_release


def _remove_entrypoints(source: Path, home: Path) -> None:
    local_bin = home / ".local" / "bin"
    backups = home / ".config" / "codex-pet" / "cli-backups"
    for name in ENTRYPOINTS:
        target = local_bin / name
        if not _is_managed_entrypoint(target, name, source):
            continue
        target.unlink(missing_ok=True)
        backup = backups / name
        if backup.exists() or backup.is_symlink():
            os.replace(backup, target)
    try:
        backups.rmdir()
    except OSError:
        pass


def remove_installation(source: Path, home: Path | None = None) -> None:
    """Remove only marked runtime releases and managed command wrappers."""
    source = source.resolve()
    home = (home or Path.home()).resolve()
    _remove_entrypoints(source, home)

    app_dir = _app_dir(home)
    if not app_dir.is_dir() or app_dir.is_symlink():
        return
    for name in (CURRENT, PREVIOUS):
        link = app_dir / name
        if link.is_symlink() and _managed_release(app_dir, os.readlink(link)) is not None:
            link.unlink()

    releases_dir = app_dir / RELEASES
    if releases_dir.is_dir() and not releases_dir.is_symlink():
        for release in releases_dir.iterdir():
            marker = release / RELEASE_MARKER
            if release.is_dir() and not release.is_symlink() and marker.is_file():
                if marker.read_text(encoding="utf-8") == "codex-pet\n":
                    shutil.rmtree(release)
        try:
            releases_dir.rmdir()
        except OSError:
            pass
    try:
        app_dir.rmdir()
    except OSError:
        pass


@dataclass(frozen=True)
class _SavedPath:
    kind: str
    contents: bytes | str | None = None
    mode: int = 0


def _save_path(path: Path) -> _SavedPath:
    if path.is_symlink():
        return _SavedPath("symlink", os.readlink(path))
    if path.is_file():
        return _SavedPath("file", path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
    if path.exists():
        raise IsADirectoryError(f"Cannot replace directory: {path}")
    return _SavedPath("missing")


def _restore_path(path: Path, saved: _SavedPath) -> None:
    if path.is_dir() and not path.is_symlink():
        raise IsADirectoryError(f"Cannot restore over directory: {path}")
    path.unlink(missing_ok=True)
    if saved.kind == "missing":
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.restore")
    try:
        if saved.kind == "symlink":
            assert isinstance(saved.contents, str)
            temporary.symlink_to(saved.contents)
        else:
            assert isinstance(saved.contents, bytes)
            temporary.write_bytes(saved.contents)
            temporary.chmod(saved.mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _install_paths(home: Path, prefix: Path) -> tuple[Path, ...]:
    app_dir = _app_dir(home)
    local_bin = home / ".local" / "bin"
    backups = home / ".config" / "codex-pet" / "cli-backups"
    prefix_bin = prefix / "bin"
    paths = [app_dir / CURRENT, app_dir / PREVIOUS,
             home / ".config" / "codex-pet" / "config.json",
             home / ".config" / "codex-pet" / "install.json",
             home / ".codex" / "config.toml", home / ".codex" / "hooks.json"]
    for name in ENTRYPOINTS:
        paths.extend((local_bin / name, backups / name,
                      prefix_bin / name, backups / f"prefix-{name}"))
    return tuple(paths)


@contextmanager
def _installation_lock(home: Path) -> Iterator[None]:
    path = home / ".config" / "codex-pet" / "install.lock"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    with open(path, "a+b") as lock:
        path.chmod(0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _install_prefix_entrypoints(home: Path, prefix: Path) -> None:
    local_bin = home / ".local" / "bin"
    prefix_bin = prefix / "bin"
    backups = home / ".config" / "codex-pet" / "cli-backups"
    prefix_bin.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ENTRYPOINTS:
        target = prefix_bin / name
        if target.is_dir() and not target.is_symlink():
            raise IsADirectoryError(f"Cannot install over directory: {target}")
    for name in ENTRYPOINTS:
        target = prefix_bin / name
        stable = local_bin / name
        backup = backups / f"prefix-{name}"
        if (target.exists() or target.is_symlink()) and not (
                target.is_symlink() and os.readlink(target) == str(stable)):
            if not backup.exists() and not backup.is_symlink():
                _copy_entrypoint_backup(target, backup)
        temporary = prefix_bin / f".{name}.{uuid4().hex}.tmp"
        try:
            temporary.symlink_to(stable)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def _remove_prefix_entrypoints(home: Path, prefix: Path) -> None:
    local_bin = home / ".local" / "bin"
    prefix_bin = prefix / "bin"
    backups = home / ".config" / "codex-pet" / "cli-backups"
    for name in ENTRYPOINTS:
        target = prefix_bin / name
        if not target.is_symlink() or os.readlink(target) != str(local_bin / name):
            continue
        target.unlink()
        backup = backups / f"prefix-{name}"
        if backup.exists() or backup.is_symlink():
            os.replace(backup, target)


def _run(command: list[str], *, input_text: str | None = None,
         quiet: bool = False) -> int:
    result = subprocess.run(command, input=input_text, text=True, check=False,
                            stdout=subprocess.DEVNULL if quiet else None,
                            stderr=subprocess.DEVNULL if quiet else None)
    return result.returncode


def _require(command: list[str], *, input_text: str | None = None) -> None:
    if _run(command, input_text=input_text) != 0:
        raise RuntimeError(f"Installation command failed: {command[0]} {command[1]}")


def _remove_new_releases(home: Path, previous: set[str]) -> None:
    releases = _app_dir(home) / RELEASES
    if not releases.is_dir():
        return
    for release in releases.iterdir():
        if release.name not in previous and release.is_dir() and not release.is_symlink():
            marker = release / RELEASE_MARKER
            if marker.is_file() and marker.read_text(encoding="utf-8") == "codex-pet\n":
                shutil.rmtree(release)


def install_application(source: Path, home: Path, prefix: Path) -> Path:
    """Install a release, hooks, and commands as one recoverable operation."""
    home, prefix = home.resolve(), prefix.resolve()
    with _installation_lock(home):
        paths = _install_paths(home, prefix)
        saved = {path: _save_path(path) for path in paths}
        releases = _app_dir(home) / RELEASES
        previous_releases = {path.name for path in releases.iterdir()} if releases.is_dir() else set()
        local_cli = str(home / ".local" / "bin" / "codex-pet")
        local_event = str(home / ".local" / "bin" / "codex-pet-event")
        old_current = saved[_app_dir(home) / CURRENT].kind == "symlink"
        try:
            was_running = old_current and _run([local_cli, "status"], quiet=True) == 0
        except OSError:
            was_running = False
        restart_attempted = False
        try:
            cache = home / ".cache" / "codex-pet"
            cache.mkdir(mode=0o700, parents=True, exist_ok=True)
            cache.chmod(0o700)
            config = home / ".config" / "codex-pet" / "config.json"
            if not config.exists():
                config.write_text('{"position":{"x":700,"y":420}}\n', encoding="utf-8")
                config.chmod(0o600)
            release = deploy(source, home)
            _install_prefix_entrypoints(home, prefix)
            hooks_config.install(home)
            restart_attempted = True
            _require([local_cli, "restart"])
            _require([local_cli, "status"])
            _require([local_event, "--state", "idle", "--session-id", SMOKE_SESSION,
                      "--project", "Codex Pet"])
            _require([local_cli, "status"])
            _require([local_event], input_text=(
                '{"hook_event_name":"SessionEnd","session_id":"install-smoke"}\n'
            ))
            print("Install and IPC smoke test complete. Review/trust hooks with /hooks in a new Codex session.")
            return release
        except BaseException as install_error:
            recovery_errors: list[str] = []
            stopped = True
            if restart_attempted:
                try:
                    stopped = _run([local_cli, "stop"], quiet=True) == 0
                except OSError:
                    stopped = False
                if not stopped:
                    recovery_errors.append("new daemon could not be stopped")
            for path, original in reversed(tuple(saved.items())):
                try:
                    _restore_path(path, original)
                except OSError as exc:
                    recovery_errors.append(f"could not restore {path}: {exc}")
            if stopped and not recovery_errors:
                try:
                    _remove_new_releases(home, previous_releases)
                except OSError as exc:
                    recovery_errors.append(f"could not remove failed release: {exc}")
            if restart_attempted and was_running and stopped and not recovery_errors:
                try:
                    if _run([local_cli, "start"]) != 0:
                        recovery_errors.append("previous daemon could not be restarted")
                except OSError as exc:
                    recovery_errors.append(f"previous daemon could not be restarted: {exc}")
            if recovery_errors:
                raise RuntimeError("Installation failed; rollback incomplete: "
                                   + "; ".join(recovery_errors)) from install_error
            raise


def uninstall_application(source: Path, home: Path, prefix: Path) -> None:
    """Remove only Pet-owned commands, hooks, runtime releases, and cache files."""
    home, prefix = home.resolve(), prefix.resolve()
    with _installation_lock(home):
        local_cli = home / ".local" / "bin" / "codex-pet"
        if _is_managed_entrypoint(local_cli, "codex-pet", source.resolve()):
            if _run([str(local_cli), "stop"]) != 0:
                raise RuntimeError("Codex Pet did not stop")
        hooks_config.uninstall(home)
        _remove_prefix_entrypoints(home, prefix)
        remove_installation(source, home)
        cache = home / ".cache" / "codex-pet"
        for name in ("pet.sock", "pet.log", "pet.log.1", "pet.log.2",
                     "start.lock", "daemon.lock"):
            (cache / name).unlink(missing_ok=True)
        try:
            cache.rmdir()
        except OSError:
            pass
    print("Codex Pet uninstalled. Python dependencies and saved position were kept.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="codex-pet-deployment")
    parser.add_argument("command", choices=("deploy", "rollback", "remove", "install", "uninstall"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--prefix", type=Path)
    args = parser.parse_args()
    if args.command in ("install", "uninstall") and args.prefix is None:
        parser.error("--prefix is required for install and uninstall")
    if args.command == "install":
        print(install_application(args.source, args.home, args.prefix))
    elif args.command == "uninstall":
        uninstall_application(args.source, args.home, args.prefix)
    elif args.command == "deploy":
        print(deploy(args.source, args.home))
    elif args.command == "rollback":
        print(rollback(args.home))
    else:
        remove_installation(args.source, args.home)


if __name__ == "__main__":
    main()
