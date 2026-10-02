#!/usr/bin/env python3
"""Opt-in device experiment; never changes the installed pet or its sessions.

Results measure submission plus a command-processing fence, NOT presentation.
All native calls run on this script's main thread and own a separate connection.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import statistics
import select
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.historical_art import _decode_rgba_png, _png, icon
from codex_pet.renderer.termux_gui import _overlay
import termuxgui as tg


class EOFGuard:
    """The 0.1.6 binding spins on recv()==b''; make this experiment bounded."""
    def __init__(self, socket):
        self.socket = socket

    def __getattr__(self, name):
        return getattr(self.socket, name)

    def recv(self, *args):
        data = self.socket.recv(*args)
        if not data:
            raise ConnectionError("Termux:GUI closed stream (binding EOF guarded)")
        return data

    def recvmsg(self, *args):
        result = self.socket.recvmsg(*args)
        if not result[0]:
            raise ConnectionError("Termux:GUI closed FD stream (binding EOF guarded)")
        return result


def connect():
    connection = tg.Connection()
    connection._main = EOFGuard(connection._main)
    connection._event = EOFGuard(connection._event)
    connection._main.settimeout(3)
    connection._event.settimeout(3)
    return connection


def summary(values: list[float]) -> dict:
    ordered = sorted(values)
    return {"n": len(values), "median_ms": statistics.median(values),
            "p95_ms": ordered[math.ceil(len(values) * .95) - 1],
            "max_ms": max(values)}


def premultiply(data: bytes) -> bytes:
    result = bytearray(data)
    for i in range(0, len(result), 4):
        alpha = result[i + 3]
        for channel in range(3):
            result[i + channel] = (result[i + channel] * alpha + 127) // 255
    return bytes(result)


def frames(width: int, height: int) -> list[tuple[bytes, bytes]]:
    """Use shipped frames, padding (never rescaling) the larger test canvas."""
    result = []
    for frame in range(2 if width == 64 else 10):
        png = icon("running", frame, 1, "robot" if width == 64 else "akita")
        w, h, pixels = _decode_rgba_png(png)
        if (w, h) != (width, height):
            target = bytearray(width * height * 4)
            dx, dy = (width - w) // 2, (height - h) // 2
            for y in range(h):
                start = ((y + dy) * width + dx) * 4
                target[start:start + w * 4] = pixels[y * w * 4:(y + 1) * w * 4]
            pixels = target
            png = _png(width, height, pixels)
        result.append((png, premultiply(pixels)))
    return result


def make_view(connection):
    activity = _overlay(connection)
    root = tg.LinearLayout(activity, vertical=False)
    root.setdimensions(tg.View.WRAP_CONTENT, tg.View.WRAP_CONTENT)
    root.setbackgroundcolor(0)
    face = tg.ImageView(activity, root)
    face.setdimensions(64, 64)
    activity.setposition(40, 140)
    time.sleep(.15)
    return activity, face


def format_probe() -> list[dict]:
    output = []
    for fmt in ("ARGB888", "ARGB8888"):
        # A rejected FD transfer must not contaminate another probe's stream.
        with connect() as connection:
            record = {"format": fmt}
            try:
                buffer = tg.Buffer(connection, 4, 4, format=fmt)
                try:
                    buffer.mem[:] = bytes([128, 0, 0, 128]) * 16
                    buffer.blit()
                    version = connection.getversion()
                    record.update({"created": True,
                                   "bytes": len(buffer.mem), "fence_version": version})
                finally:
                    buffer.remove()
                    record["after_remove"] = connection.getversion()
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            output.append(record)
            print(json.dumps(record), flush=True)
    return output


def benchmark(connection, activity, face, prepared, size, mode, count, paced, shared):
    buffer = None
    if mode == "shared":
        buffer = shared
        face.setbuffer(buffer)
        face.getdimensions()  # UI queue barrier at setup, outside measurement.
    samples = []
    lateness = []
    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    try:
        for index in range(count + 5):
            if paced:
                deadline = start_wall + index / 25
                time.sleep(max(0, deadline - time.perf_counter()))
                lateness.append(max(0, time.perf_counter() - deadline) * 1000)
            png, rgba = prepared[index % len(prepared)]
            before = time.perf_counter()
            if buffer is None:
                face.setimage(png)
            else:
                buffer.mem[:] = rgba
                buffer.blit()
                face.refresh()
            if paced:
                activity.setposition(40 + index % 20, 140)
            # 0.1.6 JSON dispatch is serial and blit copies synchronously.
            # This fences mmap consumption, but not Android's actual display.
            connection.getversion()
            elapsed = (time.perf_counter() - before) * 1000
            if index >= 5:
                samples.append(elapsed)
        record = {"size": list(size), "mode": mode,
                  "workload": "25_hz_with_move" if paced else "unpaced",
                  "submission_fence": summary(samples),
                  "python_cpu_ms": (time.process_time() - start_cpu) * 1000,
                  "wall_ms": (time.perf_counter() - start_wall) * 1000,
                  "png_bytes_mean": statistics.mean(len(p[0]) for p in prepared),
                  "rgba_bytes": len(prepared[0][1])}
        if paced:
            record["wakeup_lateness"] = summary(lateness[5:])
        return record
    finally:
        if buffer is not None:
            face.setimage(prepared[0][0])
            face.getdimensions()  # Detach before freeing the shared resource.
            # Keep native buffer alive until connection close: deleting the
            # last transferred FD breaks later replies on the tested APK.


def run(args):
    report = {"schema": 1, "python": platform.python_version(),
              "platform": platform.platform(),
              "binding": importlib.metadata.version("termuxgui"),
              "metric_scope": "submission plus getVersion command fence, not display latency",
              "other_live_pet": "left running; no session or configuration changes",
              "formats": format_probe(), "benchmarks": []}
    prepared = {size: frames(*size) for size in ((64, 64), (256, 256), (384, 416))}
    report["fd_before"] = len(os.listdir("/proc/self/fd"))
    with connect() as connection:
        report["plugin_version_code"] = connection.getversion()
        report["locked"] = connection.islocked()
        activity, face = make_view(connection)
        try:
            report["view_dimensions_px"] = face.getdimensions()
            samples = []
            for _ in range(100):
                before = time.perf_counter()
                connection.getversion()
                samples.append((time.perf_counter() - before) * 1000)
            report["empty_fence"] = summary(samples)
        finally:
            activity.finish()
            connection.getversion()
    for trial in range(args.trials):
        for size, data in prepared.items():
            with connect() as connection:
                activity, face = make_view(connection)
                shared = tg.Buffer(connection, *size, format="ARGB888")
                try:
                    # Alternate path order to reduce consistent warmup bias.
                    modes = ("png", "shared") if trial % 2 == 0 else ("shared", "png")
                    for mode in modes:
                        for paced in (False, True):
                            result = benchmark(connection, activity, face, data, size,
                                               mode, args.samples if not paced else 30, paced, shared)
                            result["trial"] = trial
                            report["benchmarks"].append(result)
                            print(size, mode, result["workload"], result["submission_fence"], flush=True)
                finally:
                    try:
                        activity.finish()
                        connection.getversion()
                    finally:
                        connection.close()
                        shared.mem.close()
                        os.close(shared.fd)
    report["fd_after"] = len(os.listdir("/proc/self/fd"))
    report["reconnect_versions"] = []
    for _ in range(3):
        with connect() as connection:
            report["reconnect_versions"].append(connection.getversion())
    return report


def lifecycle():
    """Exercise failure/recovery on disposable connections, with finite reads."""
    report = {"scope": "native API failure behavior; no production daemon changes"}
    with connect() as connection:
        first = tg.Buffer(connection, 4, 4, format="ARGB888")
        latest = tg.Buffer(connection, 4, 4, format="ARGB888")
        report["created_two"] = connection.getversion()
        first.remove()
        report["after_remove_older"] = connection.getversion()
        latest.remove()
        try:
            report["after_remove_latest"] = connection.getversion()
        except Exception as exc:
            report["latest_error"] = f"{type(exc).__name__}: {exc}"
    with connect() as connection:
        try:
            activity = tg.Activity(connection, overlay=True)
            report["binding_overlay_constructor"] = "unexpected success"
            activity.finish()
        except Exception as exc:
            report["binding_overlay_constructor"] = f"{type(exc).__name__}: {exc}"
    with connect() as connection:
        activity = _overlay(connection)
        start = time.perf_counter()
        try:
            report["overlay_configuration"] = connection.send_read_msg(
                {"method": "getConfiguration", "params": {"aid": activity.aid}})
        except Exception as exc:
            report["overlay_configuration"] = f"{type(exc).__name__}: {exc}"
            report["configuration_wait_ms"] = (time.perf_counter() - start) * 1000
        # Deliberately discard connection after timeout; never read again.
    with connect() as connection:
        report["fresh_connection_version"] = connection.getversion()
    return report


def visual(seconds: int):
    """Two equal 64 dp views over alternating dark/light backgrounds."""
    data = frames(256, 256)
    report = {"seconds": seconds, "touch_events": [], "moves": 0,
              "scope": "human comparison required; command success is not visual acceptance"}
    with connect() as connection:
        activity = _overlay(connection)
        root = tg.LinearLayout(activity, vertical=False)
        root.setdimensions(tg.View.WRAP_CONTENT, tg.View.WRAP_CONTENT)
        views = []
        for label in ("PNG", "BUFFER"):
            column = tg.LinearLayout(activity, root, vertical=True)
            heading = tg.TextView(activity, label, column)
            heading.settextcolor(0xff000000)
            heading.setbackgroundcolor(0xffffffff)
            face = tg.ImageView(activity, column)
            face.setdimensions(64, 64)
            face.sendtouchevent(True)
            views.append(face)
        activity.setposition(40, 140)
        activity.sendoverlayevents(True)
        buffer = tg.Buffer(connection, 256, 256, format="ARGB888")
        views[1].setbuffer(buffer)
        time.sleep(.2)
        report["view_dimensions"] = views[0].getdimensions()
        x, y, down = 40, 140, None
        start = time.monotonic()
        deadline = start
        current_frame = 0
        background = None
        # Existing running schedule in logical frame order.
        durations = [.04, .04, .08, .08, .08, .04, .04, .08, .08, .08]
        print("VISUAL READY: left PNG, right BUFFER; drag either icon; dark/light every 10 seconds", flush=True)
        try:
            while time.monotonic() - start < seconds:
                now = time.monotonic()
                color = 0xff202020 if int((now - start) / 10) % 2 == 0 else 0xffffffff
                if color != background:
                    root.setbackgroundcolor(color)
                    background = color
                if now >= deadline:
                    png, rgba = data[current_frame]
                    views[0].setimage(png)
                    buffer.mem[:] = rgba
                    buffer.blit()
                    views[1].refresh()
                    connection.getversion()
                    deadline = now + durations[current_frame]
                    current_frame = (current_frame + 1) % len(data)
                readable, _, _ = select.select([connection._event], [], [], max(0, min(.05, deadline - time.monotonic())))
                if not readable:
                    continue
                event = connection.checkevent()
                if event is None or event.type != tg.Event.overlaytouch:
                    continue
                value = event.value
                action = value.get("action")
                if len(report["touch_events"]) < 100:
                    report["touch_events"].append(action)
                if action == "down":
                    down = (float(value["x"]), float(value["y"]), x, y)
                elif action == "move" and down is not None:
                    dx, dy = float(value["x"]) - down[0], float(value["y"]) - down[1]
                    if dx * dx + dy * dy > 36:
                        x, y = max(0, round(down[2] + dx)), max(0, round(down[3] + dy))
                        activity.setposition(x, y)
                        report["moves"] += 1
                elif action in ("up", "cancel"):
                    down = None
        finally:
            try:
                views[1].setimage(data[0][0])
                views[1].getdimensions()
                report["before_connection_close"] = connection.getversion()
            finally:
                try:
                    activity.finish()
                finally:
                    connection.close()
                    buffer.mem.close()
                    os.close(buffer.fd)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--visual-seconds", type=int, default=0,
                        help="Run a side-by-side draggable visual check instead of benchmarks")
    parser.add_argument("--timeout-seconds", type=int, default=180,
                        help="Whole-process watchdog, including the binding connection handshake")
    parser.add_argument("--lifecycle-only", action="store_true",
                        help="Test FD deletion, overlay constructor/configuration and fresh reconnect")
    args = parser.parse_args()
    if args.samples < 1 or args.trials < 1 or args.timeout_seconds < 1:
        parser.error("samples, trials and timeout must be positive")
    def timed_out(signum, frame):
        raise TimeoutError("device experiment exceeded whole-process deadline")
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(args.timeout_seconds)
    try:
        result = (lifecycle() if args.lifecycle_only else
                  visual(args.visual_seconds) if args.visual_seconds > 0 else run(args))
    finally:
        signal.alarm(0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
