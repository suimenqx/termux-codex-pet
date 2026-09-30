"""Atomic, merge-preserving access to the user's Pet configuration."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any, Callable

from .pets import APPEARANCE_BY_ID, DEFAULT_APPEARANCE


def read_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update_config(path: Path, update: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with open(lock_path, "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        temp = path.with_name(path.name + ".tmp")
        try:
            data = read_config(path)
            update(data)
            with open(temp, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temp, 0o600)
            os.replace(temp, path)
            return data
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass
            fcntl.flock(lock, fcntl.LOCK_UN)


def selected_appearance(path: Path) -> str:
    value = read_config(path).get("appearance", DEFAULT_APPEARANCE)
    return value if isinstance(value, str) and value in APPEARANCE_BY_ID else DEFAULT_APPEARANCE


def save_appearance(path: Path, appearance: str) -> dict[str, Any]:
    if appearance not in APPEARANCE_BY_ID:
        raise ValueError(f"Unknown pet appearance: {appearance}")
    return update_config(path, lambda data: data.__setitem__("appearance", appearance))


def save_position(path: Path, x: int, y: int) -> dict[str, Any]:
    def update(data: dict[str, Any]) -> None:
        data["position"] = {"x": x, "y": y}

    return update_config(path, update)
