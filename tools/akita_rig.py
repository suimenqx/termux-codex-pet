"""Deterministic Akita motion and skinning geometry (no raster dependencies)."""

from __future__ import annotations

import json
import math
from pathlib import Path

from codex_pet.animation import AKITA_FRAME_INTERVALS, AKITA_READY_LOOP_START

MODEL_PATH = Path(__file__).resolve().parents[1] / "docs/artwork/akita/rig-v1/model.json"
Point = tuple[float, float]


def load_model(path: Path = MODEL_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def rotate(point: Point, angle: float) -> Point:
    c, s = math.cos(angle), math.sin(angle)
    return c * point[0] - s * point[1], s * point[0] + c * point[1]


def smooth(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def mix(a: Point, b: Point, amount: float) -> Point:
    return a[0] + (b[0] - a[0]) * amount, a[1] + (b[1] - a[1]) * amount


def rigid(point: Point, pivot: Point, offset: Point, angle: float) -> Point:
    return add(add(pivot, offset), rotate(sub(point, pivot), angle))


def solve_ik(root: Point, end: Point, upper: float, lower: float, bend: int) -> Point:
    """Solve a fixed-length two-bone chain; reject unreachable authoring targets."""
    dx, dy = sub(end, root)
    distance = math.hypot(dx, dy)
    if not abs(upper - lower) + 1e-7 < distance < upper + lower - 1e-7:
        raise ValueError(f"unreachable limb: distance={distance:.4f}, lengths={upper}, {lower}")
    along = (upper * upper - lower * lower + distance * distance) / (2 * distance)
    height = math.sqrt(max(0, upper * upper - along * along)) * bend
    return (root[0] + (along * dx - height * dy) / distance,
            root[1] + (along * dy + height * dx) / distance)


def gait_foot(leg: dict, phase: float) -> tuple[Point, bool, float]:
    """A backward support stroke and C1 swing arc in the fixed overlay canvas."""
    local = (phase - leg["contact_phase"]) % 1.0
    stance, stride = leg["stance"], leg["stride"]
    base_x, base_y = leg["paw"]
    if local < stance:
        return (base_x + stride * (0.5 - local / stance), base_y), True, 0.0
    u = (local - stance) / (1 - stance)
    # Match the negative support velocity at both ends. The paw first retracts
    # after takeoff, swings forward, then retracts again just before contact.
    tangent = -stride * (1 - stance) / stance
    h00, h10 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u
    h01, h11 = -2 * u**3 + 3 * u**2, u**3 - u**2
    x = h00 * (-stride / 2) + h10 * tangent + h01 * (stride / 2) + h11 * tangent
    lift = leg["lift"] * math.sin(math.pi * u) ** 2
    angle = math.radians(12) * math.sin(2 * math.pi * u) * math.sin(math.pi * u) ** 2
    return (base_x + x, base_y - lift), False, angle


def _rest(t: float) -> tuple[float, float, float, float]:
    period = sum(AKITA_FRAME_INTERVALS["idle"])
    t %= period
    phase = t / period * 2 * math.pi
    blink = math.sin(math.pi * (t - 2.4) / .16) ** 2 if 2.4 < t < 2.56 else 0.0
    return 1.0 * math.sin(phase), .6 * math.sin(phase), math.radians(7) * math.sin(phase), blink


def pose_at(model: dict, state: str, t: float) -> dict:
    """Evaluate a continuous clip. Time-zero and loop endpoints are meaningful."""
    if state not in AKITA_FRAME_INTERVALS:
        raise ValueError(f"unknown clip: {state}")
    body_y = head_y = body_angle = head_angle = tail_angle = blink = 0.0
    flight_y = tuck = wave = 0.0
    ready_entry = sum(AKITA_FRAME_INTERVALS["ready"][:AKITA_READY_LOOP_START])
    if state == "idle" or (state == "ready" and t >= ready_entry - 1e-8):
        rest_t = t if state == "idle" else max(0.0, t - ready_entry)
        body_y, head_y, tail_angle, blink = _rest(rest_t)
    elif state == "running":
        phase = t / sum(AKITA_FRAME_INTERVALS[state]) % 1.0
        body_y = 2.2 * math.cos(4 * math.pi * (phase - .12))
        body_angle = math.radians(1.8) * math.sin(2 * math.pi * phase)
        head_y = .7 * math.sin(4 * math.pi * phase)
        head_angle = -body_angle * .35
        tail_angle = math.radians(8) * math.sin(2 * math.pi * (phase - .10))
    elif state == "needs_input":
        t %= sum(AKITA_FRAME_INTERVALS[state])
        wave = smooth(t / .35) if t < .35 else 1 - smooth((t - 1.48) / .35)
        body_y = .5 * math.sin(t / 2.4 * 2 * math.pi)
        head_y = .3 * math.sin(t / 2.4 * 2 * math.pi)
        head_angle = math.radians(-3) * wave
        tail_angle = math.radians(5) * math.sin(t / 2.4 * 2 * math.pi)
    elif state == "ready":
        if .12 <= t < .36:
            body_y = 4 * smooth((t - .12) / .24)
        elif .36 <= t < .40:
            body_y = 4 * (1 - (t - .36) / .04)
        elif .40 <= t < .90:
            u = (t - .40) / .50
            flight_y = -14 * 4 * u * (1 - u)
            tuck = 4 * math.sin(math.pi * u)
            body_y = flight_y
            body_angle = math.radians(-2) * math.sin(2 * math.pi * u)
        elif .90 <= t < 1.12:
            body_y = 3 * math.sin(math.pi * (t - .90) / .22)
        head_y = body_y * .88
        head_angle = -body_angle * .5
        tail_angle = math.radians(8) * math.sin(2 * math.pi * t / ready_entry)
    elif state == "blocked":
        u = smooth(t / .65)
        head_angle = math.radians(9) * u
        head_y = -.8 * u
        body_y = .5 * math.sin(math.pi * u)
        tail_angle = math.radians(-7) * u
        blink = .35 * math.sin(math.pi * min(1, max(0, (t - .3) / .3))) ** 2

    pose = {
        "state": state, "time_seconds": t,
        "body": {"offset": [0.0, body_y], "angle": body_angle, "scale": 1.0},
        "head": {"offset": [0.0, head_y], "angle": head_angle, "scale": 1.0},
        "tail": {"offset": [0.0, body_y], "angle": tail_angle, "scale": 1.0},
        "blink": blink, "legs": {},
    }
    for name, leg in model["legs"].items():
        bind = model["limb_bind"][leg["kind"]]
        root = rigid(leg["root"], model["body_pivot"], (0.0, body_y), body_angle)
        paw, contact, foot_angle = tuple(leg["paw"]), True, 0.0
        if state == "running":
            paw, contact, foot_angle = gait_foot(leg, phase)
        elif state == "needs_input" and name == "fore_near":
            gesture = (math.sin(4 * math.pi * (t - .35) / .48)
                       * math.sin(math.pi * (t - .35) / .48) ** 2
                       if .35 < t < .83 else 0.0)
            paw = mix(paw, (208 + 2 * gesture, 175 + 3 * gesture), wave)
            contact = wave < 1e-8
            foot_angle = math.radians(-22 - 8 * gesture) * wave
        elif state == "ready" and flight_y < 0:
            paw = add(paw, (0.0, flight_y - tuck))
            contact = False
            foot_angle = math.radians(-6 if leg["kind"] == "fore" else 6) * tuck / 4
        projection = leg["projection"]
        foot_delta = rotate(sub(bind["paw"], bind["ankle"]), foot_angle)
        ankle = sub(paw, (foot_delta[0] * projection, foot_delta[1] * projection))
        upper = math.dist(bind["root"], bind["knee"]) * projection
        lower = math.dist(bind["knee"], bind["ankle"]) * projection
        try:
            knee = solve_ik(root, ankle, upper, lower, bind["bend"])
        except ValueError as error:
            raise ValueError(f"{state} t={t:.5f} {name}: {error}") from error
        pose["legs"][name] = {
            "root": root, "knee": knee, "ankle": ankle, "paw": paw,
            "contact": contact, "foot_angle": foot_angle,
            "bone_lengths": [upper, lower], "projection": projection,
            "ground_y": leg["paw"][1] + (bind["sole"] - bind["paw"][1]) * projection,
        }
    return pose


def bone_point(point: Point, bind: dict, leg_pose: dict, bone: int) -> Point:
    """Map a fixed skin patch through one rigid bone; no texture folding."""
    keys = ("root", "knee", "ankle")
    origin = bind[keys[bone]]
    target = leg_pose[keys[bone]]
    if bone < 2:
        next_key = keys[bone + 1]
        source_delta = sub(bind[next_key], origin)
        target_delta = sub(leg_pose[next_key], target)
        angle = (math.atan2(target_delta[1], target_delta[0])
                 - math.atan2(source_delta[1], source_delta[0]))
    else:
        angle = leg_pose["foot_angle"]
    delta = rotate(sub(point, origin), angle)
    scale = leg_pose["projection"]
    return add(target, (delta[0] * scale, delta[1] * scale))


def skin_point(point: Point, bind: dict, leg_pose: dict) -> Point:
    """Landmarks belong to one of the three overlapping rigid skin patches."""
    bone = 0 if point[1] < bind["knee"][1] else (1 if point[1] < bind["ankle"][1] else 2)
    return bone_point(point, bind, leg_pose, bone)


def clip_poses(model: dict, state: str) -> list[dict]:
    elapsed = 0.0
    result = []
    rest_poses = clip_poses(model, "idle") if state == "ready" else []
    for frame, seconds in enumerate(AKITA_FRAME_INTERVALS[state]):
        if state == "ready" and frame >= AKITA_READY_LOOP_START:
            # Share the exact rest sample, including floating-point inputs.
            # Adding/subtracting the entry duration can otherwise move an
            # affine sample across a raster rounding boundary at fur edges.
            pose = rest_poses[frame - AKITA_READY_LOOP_START]
            pose.update(state=state, time_seconds=elapsed)
        else:
            pose = pose_at(model, state, elapsed)
        pose.update(frame=frame, seconds=seconds)
        result.append(pose)
        elapsed += seconds
    return result
