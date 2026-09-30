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
| Session model | `codex_pet/state.py` | Defensive event normalization, session priority, turn ordering, counts |
| Android UI | `codex_pet/gui.py`, `codex_pet/art.py` | Single robot icon overlay, GUI connection, touch, saved position, PNG frames |

The two `bin` scripts add the checkout to `sys.path`; the installed CLI entries are symlinks into this repository. A running daemon retains imported code until restarted. Moving the checkout requires reinstalling the links.

## Contracts to preserve

- **Fail open at the hook boundary.** `codex-pet-event` reads at most 64 KiB of hook JSON, tolerates missing fields, exits successfully on Pet failure, and never changes a Codex permission or execution decision. It attempts a short socket request, starts a missing daemon under `start.lock`, retries, then falls back to a notification for needs-input/ready. Keep hook work bounded.
- **One daemon.** `daemon.lock` prevents duplicates; `start.lock` serializes simultaneous hook starts. The daemon removes a stale socket before bind and removes its own socket on shutdown. Requests and replies are one newline-terminated JSON object, capped at 64 KiB. IPC actions are `event`, `status`, `reconnect`, and `stop`.
- **Session state follows observed lifecycle signals.** `SessionStore` holds a map keyed by `session_id`; `SessionEnd` deletes one entry. User-facing states use the official Pet names `needs_input`, `blocked`, `ready`, and `running`, with `idle` when no activity is active. Selection priority is needs input, blocked, ready, running, idle. `PostToolUse` returns a same-turn permission request to running; `Stop` sets ready, which stays until a later event changes that session or `SessionEnd` removes it. Tapping the icon does not alter session state. Turn IDs reject late events from superseded turns. `SessionStart` from compaction is ignored because it occurs during active work; `Interrupt` returns the session to idle. The hook API does not report final turn success/failure or unread state, so hooks never infer `blocked`; that state is currently available only to explicit/test events. Only the Pet's dragged position is persisted.
- **GUI belongs to its worker thread.** Daemon events wake `GuiWorker` through a socketpair; native Termux:GUI calls stay in that worker. Idle waits on `select`, while running/needs-input use low-frequency timed frames. On GUI disconnect, the worker logs, reports unavailability, and reconnects with backoff; the daemon can send a deduplicated Android notification for needs-input/ready while the GUI is unavailable.
- **User configuration is merged.** The installer chooses inline `config.toml` hooks when the existing config already has a `hooks` table; otherwise it uses `hooks.json`. It records its choice and created entries in `~/.config/codex-pet/install.json` so uninstall can remove its own hooks. Back up any changed user file and preserve unrelated hooks and settings.

## Overlay and touch details

`OverlayUI` keeps one 64 dp robot `ImageView` in one native overlay. There are no text views, detail cards, speech tails, or secondary overlays. The face, accent color, and small badge in `art.icon()` carry the selected state. `self.x`/`self.y` are the robot's logical screen position; the overlay moves only during a drag. The overlay belongs to the GUI worker thread.

Termux:GUI emits an overlay-wide touch event with screen coordinates and a View touch event identifying the actual target. Route View events by overlay activity ID as well as view ID. Overlay-wide touch events can omit the activity ID, so accept an absent ID and reject only an explicit ID belonging to another overlay. The View event gates drag recognition. A tap has no action; a drag starts within the central 27 dp radius after 12 dp of movement. The saved starting position plus the screen-coordinate delta keeps the original grab point under the finger, without snapping the robot to the finger's center. Releasing saves the new position; a cancelled gesture restores its start. The View touch payload's `pointers` are nested arrays; the image pixel coordinate supplies a drag anchor when Android clamps the overlay window. Apply that anchor only after movement passes the drag threshold so a tap never changes the logical position.

The installed Python binding's `Activity` constructor expects a normal activity response, but overlay creation returns only an activity ID. `_overlay()` uses the protocol call directly. The overlay's `getConfiguration` reply is unreliable on this device, so density is measured once from the native root width. Avoid blocking native dimension queries during `render()`. Check the installed binding source before relying on a new API: `python -c 'import termuxgui; print(termuxgui.__file__)'`.

## Verification by change area

| Change | Evidence before completion |
| --- | --- |
| Session or event mapping | Add a focused state/parser test; cover missing JSON fields, official priority, turn ordering, Ready persistence through later events, and SessionEnd as applicable; run the full suite |
| IPC, startup, or hooks | Exercise concurrent start/stale socket or config preservation in isolated fixtures; confirm the hook helper returns promptly on failure; run the full suite |
| GUI layout, art, or touch | Add an icon-only binding or touch regression test; run the full suite; on a Termux device run `codex-pet restart`, `codex-pet status`, `codex-pet test`; inspect the log and verify the actual gesture or state visually |
| Install or uninstall | Test against temporary user configuration, including existing unrelated hooks and repeated install/remove; use the real device only for the final smoke check |

Current automated tests under `tests/` cover GUI touch, native binding calls, and GUI reconnection. Add state, IPC, or installer tests when changing those paths. `codex-pet test` cycles through states but cannot prove a physical touch gesture; record whether that was checked by a person. Android overlay permission must be granted in Termux:GUI by the user.

For a live diagnostic, `codex-pet status` shows process and GUI health. From this checkout, `python -c 'from codex_pet.runtime import request; print(request({"action": "status"})["overlay"])'` also shows logical position and touch count. `codex-pet test` checks displayed states most strictly when it is the only session; another active session can win the priority selection, so end or isolate other sessions before judging the visual sequence.
