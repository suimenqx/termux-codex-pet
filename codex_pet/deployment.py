"""Install an immutable runtime copy independent of the editable checkout."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import stat
import tempfile
from uuid import uuid4

APP_RELATIVE = Path(".local/share/codex-pet")
RELEASES = "releases"
CURRENT = "current"
PREVIOUS = "previous"
RELEASE_MARKER = ".codex-pet-release"
ENTRYPOINTS = ("codex-pet", "codex-pet-event")
ENTRYPOINT_MARKER = "# CODEX_PET_MANAGED_ENTRYPOINT="


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="codex-pet-deployment")
    parser.add_argument("command", choices=("deploy", "rollback", "remove"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args()
    if args.command == "deploy":
        print(deploy(args.source, args.home))
    elif args.command == "rollback":
        print(rollback(args.home))
    else:
        remove_installation(args.source, args.home)


if __name__ == "__main__":
    main()
