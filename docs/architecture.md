# Architecture and change map

This is the reference for agents changing hook ingestion, sessions, IPC, daemon lifecycle, native overlay layout or touch, and install/uninstall behavior. Read the relevant section, then inspect the owning code and its tests; code remains authoritative for exact values.

## Event path and ownership

```text
Codex lifecycle hook JSON on stdin
  → bin/codex-pet-event → cli.event_main → state.event_from_hook
  → runtime.request over ~/.cache/codex-pet/pet.sock
  → daemon.Daemon.process → state.SessionStore
  → GuiWorker wake socket → OverlayUI.render → Termux:GUI overlay
```

| Boundary | Owner | What it owns |
| --- | --- | --- |
| Hook configuration | `codex_pet/hooks_config.py`, `install.sh`, `uninstall.sh` | Merge/remove only Pet hooks; back up changed Codex files |
| Hook entrypoint and human CLI | `bin/*`, `codex_pet/cli.py` | Fail-open JSON parsing, bounded send/restart, start/stop/status/test |
| Process and IPC | `codex_pet/runtime.py`, `codex_pet/daemon.py` | Paths, locks, Unix socket, signals, log rotation, notification fallback |
| Session model | `codex_pet/state.py` | Defensive event normalization, session priority, deadlines, counts |
| Android UI | `codex_pet/gui.py`, `codex_pet/art.py` | Robot and bubble overlays, GUI connection, touch, saved position, PNG frames |

The two `bin` scripts add the checkout to `sys.path`; the installed CLI entries are symlinks into this repository. A running daemon retains imported code until restarted. Moving the checkout requires reinstalling the links.

## Contracts to preserve

- **Fail open at the hook boundary.** `codex-pet-event` reads at most 64 KiB of hook JSON, tolerates missing fields, exits successfully on Pet failure, and never changes a Codex permission or execution decision. It attempts a short socket request, starts a missing daemon under `start.lock`, retries, then falls back to a notification for approval/done. Keep hook work bounded.
- **One daemon.** `daemon.lock` prevents duplicates; `start.lock` serializes simultaneous hook starts. The daemon removes a stale socket before bind and removes its own socket on shutdown. Requests and replies are one newline-terminated JSON object, capped at 64 KiB. IPC actions are `event`, `status`, `reconnect`, and `stop`.
- **Sessions are transient.** `SessionStore` holds a map keyed by `session_id`; `SessionEnd` deletes one entry. Selection priority is approval, working, error, done, interrupted, idle. Done/interrupted expire by monotonic deadlines. Only the Pet's dragged position is persisted. An error icon exists for direct test events; lifecycle hooks do not infer errors.
- **GUI belongs to its worker thread.** Daemon events wake `GuiWorker` through a socketpair; native Termux:GUI calls stay in that worker. Idle waits on `select`, while working/approval use low-frequency timed frames. On GUI disconnect, the worker logs, reports unavailability, and reconnects with backoff; the daemon can send a deduplicated Android notification for approval/done while the GUI is unavailable.
- **User configuration is merged.** The installer chooses inline `config.toml` hooks when the existing config already has a `hooks` table; otherwise it uses `hooks.json`. It records its choice and created entries in `~/.config/codex-pet/install.json` so uninstall can remove its own hooks. Back up any changed user file and preserve unrelated hooks and settings.

## Overlay and touch details

`OverlayUI` keeps the robot in a 64 dp `ImageView` in its own native overlay. A second overlay contains one of two detail cards, placed left or right of the robot, and its speech tail. Include the tail width in side selection and bubble positioning so its tip touches the robot. `self.x`/`self.y` are the robot's logical screen position. The robot overlay moves only during a drag; opening or closing the bubble moves and resizes the separate bubble overlay, leaving the robot window stationary. Both overlays belong to the same GUI worker thread.

Termux:GUI emits an overlay-wide touch event with screen coordinates and a View touch event identifying the actual target. Route View events by overlay activity ID as well as view ID; view IDs can overlap between the robot and bubble overlays. Overlay-wide touch events can omit the activity ID, so accept an absent ID and reject only an explicit ID belonging to another overlay. The View event gates drag/tap so touching the card cannot move the robot. Taps work across the robot's `ImageView`; a drag starts within the central 27 dp radius after 12 dp of movement, making more of the face easy to grab while corner taps remain taps. The saved starting position plus the screen-coordinate delta keeps the original grab point under the finger, without snapping the robot to the finger's center. Releasing saves the new position; a cancelled gesture restores its start. The View touch payload's `pointers` are nested arrays; the image pixel coordinate supplies a drag anchor when Android clamps the overlay window. Apply that anchor only after movement passes the drag threshold so a tap never changes the logical position. A manual card tap overrides automatic closing; approval and done open the card on state changes.

The installed Python binding's `Activity` constructor expects a normal activity response, but overlay creation returns only an activity ID. `_overlay()` uses the protocol call directly. The overlay's `getConfiguration` reply is unreliable on this device, so density is measured once from the native root width. Avoid blocking native dimension queries during `render()`. Check the installed binding source before relying on a new API: `python -c 'import termuxgui; print(termuxgui.__file__)'`.

## Verification by change area

| Change | Evidence before completion |
| --- | --- |
| Session or event mapping | Add a focused state/parser test; cover missing JSON fields, priority, expiry, and SessionEnd as applicable; run the full suite |
| IPC, startup, or hooks | Exercise concurrent start/stale socket or config preservation in isolated fixtures; confirm the hook helper returns promptly on failure; run the full suite |
| GUI layout, art, or touch | Add a touch/binding regression test; run the full suite; on a Termux device run `codex-pet restart`, `codex-pet status`, `codex-pet test`; inspect the log and verify the actual gesture or state visually |
| Install or uninstall | Test against temporary user configuration, including existing unrelated hooks and repeated install/remove; use the real device only for the final smoke check |

Current automated tests under `tests/` cover GUI touch, native binding calls, and GUI reconnection. Add state, IPC, or installer tests when changing those paths. `codex-pet test` cycles through states but cannot prove a physical touch gesture; record whether that was checked by a person. Android overlay permission must be granted in Termux:GUI by the user.

For a live diagnostic, `codex-pet status` shows process and GUI health. From this checkout, `python -c 'from codex_pet.runtime import request; print(request({"action": "status"})["overlay"])'` also shows logical position, expanded card, and touch count. `codex-pet test` checks displayed states most strictly when it is the only session; another active session can win the priority selection, so end or isolate other sessions before judging the visual sequence.
