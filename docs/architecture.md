# Architecture and change map

This is the reference for agents changing hook ingestion, sessions, IPC, daemon lifecycle, native overlay layout or touch, and install/uninstall behavior. Read the relevant section, then inspect the owning code and its tests; code remains authoritative for exact values.

## Event path and ownership

```text
Codex lifecycle hook JSON on stdin
  → bin/codex-pet-event → hook.event_main → state.event_from_hook
  → runtime.send_event / runtime.request over ~/.cache/codex-pet/pet.sock
  → daemon.Daemon.process → state.SessionStore
  → GuiWorker wake socket → AnimationTimeline → OverlayUI.render → Termux:GUI overlay
```

| Seam | Owner | What it owns |
| --- | --- | --- |
| Hook configuration | `codex_pet/hooks_config.py`, `install.sh`, `uninstall.sh` | Merge/remove only Pet hooks; back up changed Codex files |
| Hook entrypoint | `bin/codex-pet-event`, `codex_pet/hook.py` | Bounded JSON parsing, fail-open handling, and hook-side notification fallback |
| Appearance catalog | `codex_pet/pets.py` | Supported IDs, default choice, source image dimensions, and renderer/animation profiles |
| Human CLI | `bin/codex-pet`, `codex_pet/cli.py`, `codex_pet/preferences.py` | Daemon controls and appearance selection; daemon code is imported only by the `daemon` command |
| Process and IPC | `codex_pet/runtime.py`, `codex_pet/daemon.py` | Paths, locks, Unix socket, event delivery and retry, signals, log rotation, notification fallback |
| Session model | `codex_pet/state.py` | Defensive event normalization, session priority, turn ordering, counts |
| Animation playback | `codex_pet/animation.py` | Per-appearance frame sequence, timing, loop/hold behavior, monotonic playback timeline, finite schedule for offline tools |
| Artwork rendering | `codex_pet/art.py`, `codex_pet/assets/` | Draw robot pixels, load Akita frames, compose badges and blink frames into PNG/RGBA images |
| Android UI | `codex_pet/gui.py`, `codex_pet/pets.py`, `codex_pet/preferences.py` | Overlay and GUI connection, touch, saved position and appearance, rendering the current playback frame |

The two `bin` scripts add the checkout to `sys.path`; the installed CLI entries are symlinks into this repository. The hook entrypoint and ordinary CLI commands do not import the daemon or Termux:GUI binding. A running daemon retains imported code until restarted. Moving the checkout requires reinstalling the links.

`pets.py` is the source of truth for each appearance's ID, default status, source image dimensions, art profile, and animation profile. `art.py` and `animation.py` implement those profiles; `gui.py` reads the registered image dimensions for touch-coordinate scaling as well as rendering.

## Contracts to preserve

- **Fail open at the hook boundary.** `codex-pet-event` reads at most 64 KiB of hook JSON, tolerates missing fields, exits successfully on Pet failure, and never changes a Codex permission or execution decision. It attempts a short socket request, starts a missing daemon under `start.lock`, retries, then falls back to a notification for needs-input/ready. Keep hook work bounded.
- **One daemon.** `daemon.lock` prevents duplicates; `start.lock` serializes simultaneous hook starts. The daemon removes a stale socket before bind and removes its own socket on shutdown. Requests and replies are one newline-terminated JSON object, capped at 64 KiB. IPC actions are `event`, `status`, `reconnect`, `set_appearance`, and `stop`. GUI outage notifications are deduplicated by state/project/message across the GUI and IPC threads; the key is reserved before invoking the external notification command, outside the daemon state lock, and cleared on GUI recovery.
- **Session state follows observed lifecycle signals.** `SessionStore` holds a map keyed by `session_id`; `SessionEnd` deletes one entry. User-facing states use the official Pet names `needs_input`, `blocked`, `ready`, and `running`, with `idle` when no activity is active. Selection priority is needs input, blocked, ready, running, idle. `PostToolUse` returns a same-turn permission request to running; `Stop` sets ready, which stays until a later event changes that session or `SessionEnd` removes it. Tapping the icon does not alter session state. Turn IDs reject late events from superseded turns. `SessionStart` from compaction is ignored because it occurs during active work; `Interrupt` returns the session to idle. The hook API does not report final turn success/failure or unread state, so hooks never infer `blocked`; that state is currently available only to explicit/test events. The selected appearance and dragged position share `~/.config/codex-pet/config.json`; Akita is the default and the original robot remains selectable.
- **GUI belongs to its worker thread.** Daemon events and appearance changes wake `GuiWorker` through a socketpair; native Termux:GUI calls stay in that worker. `animation.AnimationTimeline` owns per-appearance frame timing, monotonic deadlines, loop/hold behavior, and late-frame skipping. The offline `playback_frames()` schedule uses the same frame progression and durations for previews and audits. `gui.py` drives the timeline and renders its current frame; image decoding and composition stay in `art.py`. The Akita loops idle, running, and needs-input frames; the eight-pose running cycle follows compression, rear support and drive, suspension, forepaw contact, support, and recovery. Idle and the Ready loop include two wider tail-sway poses. Ready uses a grounded crouch before one relaxed hop on entry, then loops slow breathing with a face-only blink. The loop does not reuse airborne jump poses. The blink composites the closed-eye area over one stable body frame so the chest does not shift with the eye pose. Blocked plays a short sequence once and holds the final frame. The robot keeps its existing animation. PNG frames are sent to the Termux:GUI `ImageView`, whose decoder premultiplies alpha before drawing. Do not copy Akita's straight-alpha RGBA pixels directly into its raw shared bitmap buffer. On GUI disconnect, the worker logs, reports unavailability, and reconnects with backoff; the daemon can send a deduplicated Android notification for needs-input/ready while the GUI is unavailable.
- **User configuration is merged.** The installer chooses inline `config.toml` hooks when the existing config has event matcher groups; Codex's `hooks.state` metadata alone does not select inline mode. Otherwise it uses `hooks.json`. It records its choice and created entries in `~/.config/codex-pet/install.json` so uninstall can remove its own hooks. Back up any changed user file and preserve unrelated hooks and settings.

## Overlay and touch details

`OverlayUI` keeps one 64 dp `ImageView` in one native overlay. There are no text views, detail cards, speech tails, or secondary overlays. `codex-pet pet list` exposes the appearance catalog; `codex-pet pet use <id>` persists a selection and updates a running daemon. `art.icon()` resolves the appearance's registered art profile and returns the PNG frame sent to the `ImageView`; `art.rgba_icon()` exposes straight-alpha Akita pixels for offline rendering and animation audits. libpng draws the running-session count badge into each Akita frame. Android's PNG decoder premultiplies the alpha before drawing. Do not send `rgba_icon()` directly to Termux:GUI's raw shared bitmap buffer, which copies bytes without premultiplying them. `self.x`/`self.y` are the mascot's logical screen position; the overlay moves only during a drag. The overlay belongs to the GUI worker thread.

Termux:GUI emits an overlay-wide touch event with absolute screen coordinates for every touch in the overlay window. Use it as the drag gesture source so recognition does not depend on the ordering of events from separate paths. A tap has no action; dragging can start anywhere on the 64 dp icon after 6 dp of movement. The saved starting position plus the screen-coordinate delta keeps the original grab point under the finger. The targeted View touch event is optional and only refines the grab anchor near screen edges; its nested `pointers` report source-image pixels, so scale those coordinates to the 64 dp view before applying them. Releasing saves the new position; a cancelled gesture restores its start. Apply anchor corrections only after touch-down, so a tap never changes the logical position.

The installed Python binding's `Activity` constructor expects a normal activity response, but overlay creation returns only an activity ID. `_overlay()` uses the protocol call directly. The overlay's `getConfiguration` reply is unreliable on this device, so density is measured once from the native root width. Avoid blocking native dimension queries during `render()`. Check the installed binding source before relying on a new API: `python -c 'import termuxgui; print(termuxgui.__file__)'`.

## Verification by change area

| Change | Evidence before completion |
| --- | --- |
| Session or event mapping | Add a focused state/parser test; cover missing JSON fields, official priority, turn ordering, Ready persistence through later events, and SessionEnd as applicable; run the full suite |
| IPC, startup, or hooks | Exercise concurrent start/stale socket or config preservation in isolated fixtures; confirm the hook helper returns promptly on failure; run the full suite |
| Animation playback | Add a deterministic `AnimationTimeline` and `playback_frames()` regression test; run the full suite |
| GUI layout, art, or touch | Add an icon-only binding or touch regression test; run the full suite; on a Termux device run `codex-pet restart`, `codex-pet status`, `codex-pet test`; inspect the log and verify the actual gesture or state visually |
| Install or uninstall | Test against temporary user configuration, including existing unrelated hooks and repeated install/remove; use the real device only for the final smoke check |

Current automated tests under `tests/` cover playback schedules, GUI touch, native binding calls, and GUI reconnection. Add state, IPC, or installer tests when changing those paths. For a visual frame review, run `python tools/preview_animation.py --state ready --cycles 2` and open the generated `~/.cache/codex-pet/preview-ready.html` in a browser. The preview uses the shared playback schedule and production PNG frames at the 64 dp overlay size; it helps spot abrupt poses before device verification. It does not emulate Termux:GUI's native ImageView or Android rendering. `codex-pet test` cycles through states but cannot prove a physical touch gesture; record whether that was checked by a person. Android overlay permission must be granted in Termux:GUI by the user.

For a live diagnostic, `codex-pet status` shows process and GUI health. From this checkout, `python -c 'from codex_pet.runtime import request; print(request({"action": "status"})["overlay"])'` also shows logical position and touch count. `codex-pet test` checks displayed states most strictly when it is the only session; another active session can win the priority selection, so end or isolate other sessions before judging the visual sequence.

For screenshot-free visual and motion checks, run `python tools/audit_animation.py --state ready --cycles 2` or `python tools/audit_animation.py --state running --cycles 2`. It renders the production `rgba_icon()` pixels with premultiplied bilinear sampling at the 64 dp overlay size (3× density by default), writes a labeled contact sheet plus individual frames, and records frame hashes, delays, transition pixel changes, tail movement, chest stability, and (for running) the two hind-paw paths relative to an orange hip anchor in `audit.json`. The running contact sheet marks the near paw in magenta and the far paw in cyan; the audit checks that each marker lands on opaque cream art and that the paws travel on distinct paths. Set `--density` to match another device. This checks the production frame pixels and schedule after display-size scaling; it does not claim to reproduce Android's exact image-filtering implementation.

For the gait rationale, pose planning, frame-art consistency, and paw-track audit workflow used for the Akita, see [the dog gait animation guide](animation-gait.md).
