# Architecture and change map

This is the reference for agents changing hook ingestion, sessions, IPC, daemon lifecycle, native overlay layout or touch, and install/uninstall behavior. Read the relevant section, then inspect the owning code and its tests; code remains authoritative for exact values.

The [measured refactor plan](research/termux-gui-refactor-plan.md) records the investigation baseline and migration gates. [Implementation evidence](research/implementation-status.md) records what has shipped and which device gates remain open. The contracts below describe the current implementation.

## Event path and ownership

```text
Codex lifecycle hook JSON on stdin
  → bin/codex-pet-event → hook.event_main → adapters.codex.event_from_hook
  → runtime.send_event / runtime.request over ~/.cache/codex-pet/pet.sock
  → daemon.Daemon.process → state.SessionStore
  → GuiWorker wake socket → PetRuntime → FrameSource/FrameComposer → TermuxGuiRenderer.present → overlay
```

| Seam | Owner | What it owns |
| --- | --- | --- |
| Hook configuration | `codex_pet/hooks_config.py` | Merge/remove only Pet hooks; back up changed Codex files |
| Runtime deployment | `codex_pet/deployment.py`, `install.sh`, `uninstall.sh` | Own the install/uninstall sequence and failure restoration; copy immutable private releases, switch active version, and manage stable command wrappers |
| Hook entrypoint | `bin/codex-pet-event`, `codex_pet/hook.py` | Bounded JSON parsing, fail-open handling, and hook-side notification fallback |
| Appearance catalog | `codex_pet/pets.py` | Supported IDs, names, descriptions and default choice; geometry and playback belong to packs |
| Human CLI | `bin/codex-pet`, `codex_pet/cli.py`, `codex_pet/preferences.py` | Daemon controls and appearance selection; daemon code is imported only by the `daemon` command |
| Process and IPC | `codex_pet/runtime.py`, `codex_pet/daemon.py` | Paths, locks, Unix socket, event delivery and retry, signals, log rotation, notification fallback |
| Session model | `codex_pet/state.py` | Semantic event application, session priority, turn ordering, counts |
| Pack and playback | `pet_pack.py`, `pet_runtime.py`, `clip_timeline.py` | Validate data, select entries/transitions, compute the current physical frame and next deadline |
| Frame preparation | `frames.py`, `drawing.py`, `image_codec.py`, `frame_cache.py` | Immutable RGBA sources, decorations, Pillow conversion and the shared byte budget |
| Android UI | `gui.py`, `touch.py`, `renderer/` | GUI-thread orchestration, pure gestures, normalized input, native windows, protocol, transport and diagnostics |

The two `bin` scripts add their containing runtime release to `sys.path`. `install.sh` checks dependencies, then `deployment.install_application()` owns release activation, stable commands, hook merging, daemon restart, smoke checks, and restoration after a checked step fails. `uninstall.sh` enters the matching removal path. Installation copies `bin/` and `codex_pet/` into an immutable release under `~/.local/share/codex-pet/releases/`, then atomically switches `current`. Stable wrappers in `~/.local/bin/` invoke that private runtime; Codex hooks keep calling the stable `codex-pet-event` path. The checkout can move or be unavailable while the installed Pet continues to run. Each daemon resolves its own release path, including artwork assets, and the previous release is retained for rollback. The hook entrypoint and ordinary CLI commands do not import the daemon or Termux:GUI binding. Startup lock acquisition and IPC retries share an absolute monotonic deadline. The project-owned renderer transport bounds broadcast, handshake, protocol messages and FD receipt, preserving peer UID validation. It discards both channels on a failed transaction. GUI wake sockets are nonblocking and coalesce notifications, never session events. IPC reads an immutable OverlayStatus published by the GUI worker rather than the live window object. A running daemon retains imported code until restarted.

Install and uninstall serialize through `~/.config/codex-pet/install.lock`. Installation records the prior managed paths before changing them; a failed checked step restores those paths, removes the new release after the new daemon stops, and restarts the prior daemon if it had been running. Codex configuration backups remain available for inspection.

`pets.py` owns the supported appearance catalog and default selection. Each validated `pet.json` owns canvas/display dimensions, frame identities and playback. There are no per-appearance art/animation profiles or duplicated geometry in the catalog.

`appearance_catalog()` merges shipped IDs with lightweight local metadata in
`~/.local/share/codex-pet/pets/catalog.json`; it imports no image or native
modules. `local_pets.import_local_pack()` validates a pack and its decoded frames,
copies referenced art and provenance into a staged private directory, and
publishes metadata under an import lock. Failed metadata publication removes
only the new pack. Imports cannot replace bundled or existing IDs and never
select the new pack. Immutable IDs preserve the compiled/frame-cache contract.
`bundled_pack()` retains its compatibility name and resolves either location;
runtime and renderer receive the same compiled pack/frame types. Installation
preflight still validates only shipped assets. Missing local directories or a
malformed catalog fall back to the normal default. The material is local user
data, outside immutable releases; reinstall/rollback/uninstall preserve it.

Offline preview/audit choices use the combined catalog. Pixel Dog (`pixel_dog`)
adds a separate bundled 64×64 PNG-directory pack:
20 unscaled poses from a CC0 sheet, including the original five-pose 650 ms run.
Its manifest maps product roles to stand, run, bark, sit-entry and sit-rest clips;
the existing 64-pixel count decoration is reused. `tools/import_pixel_dog.py`
reproduces it from archived artwork and refuses to overwrite a directory. See
the [import brief](artwork/pixel_dog/2026-10-import/brief.md) for source and timing
provenance. Akita remains the default; installing additional packs preserves the
saved appearance and position. No renderer, session or touch branch is needed
for this pet.

## Contracts to preserve

- **Fail open at the hook boundary.** `codex-pet-event` reads at most 64 KiB of hook JSON, tolerates missing fields, exits successfully on Pet failure, and never changes a Codex permission or execution decision. It attempts a short socket request, starts a missing daemon under `start.lock`, retries, then falls back to a notification for needs-input/ready. Keep hook work bounded.
- **One daemon.** `daemon.lock` prevents duplicates; `start.lock` serializes simultaneous hook starts. The daemon removes a stale socket before bind and removes its own socket on shutdown. Requests and replies are one newline-terminated JSON object, capped at 64 KiB. IPC actions are `event`, `status`, `reconnect`, `set_appearance`, and `stop`. GUI outage notifications are deduplicated by state/project/message across the GUI and IPC threads; the key is reserved before invoking the external notification command, outside the daemon state lock, and cleared on GUI recovery.
- **Session state follows observed lifecycle signals.** `SessionStore` holds a map keyed by `session_id`; `SessionEnd` deletes one entry. User-facing states use the official Pet names `needs_input`, `blocked`, `ready`, and `running`, with `idle` when no activity is active. Selection priority is needs input, blocked, ready, running, idle. `PostToolUse` returns a same-turn permission request to running; `Stop` sets ready and closes the turn; `Interrupt` sets idle and closes it. The Adapter preserves hook diagnostics and converts lifecycle evidence to semantic kinds; the store rejects late activity after a turn_end without inspecting hook names. Legacy IPC fields remain accepted at the Adapter boundary. A new `UserPromptSubmit` clears completion (and clears an obsolete ID if the new prompt has none); explicit manual events still support state demonstrations. An unknown stored turn ID adopts the first observed ID, including on Stop. A known different ID still requires a new prompt. The event response reports `applied` separately from successful transport, and status exposes the selected `turn_id` for diagnosis. Tapping the icon does not alter session state. Turn IDs reject late events from superseded turns. `SessionStart` from compaction is ignored because it occurs during active work; `Interrupt` returns the session to idle. The hook API does not report final turn success/failure or unread state, so hooks never infer `blocked`; that state is currently available only to explicit/test events. The selected appearance and dragged position share `~/.config/codex-pet/config.json`; Akita is the default and the original robot remains selectable.
- **GUI belongs to its worker thread.** Nonblocking wake notifications coalesce; business events do not. `PetRuntime` receives an immutable visible state and monotonic time, selecting a physical `FrameRequest` and deadline from compiled clips. `FrameSource` and `FrameComposer` produce immutable RGBA bytes; `TermuxGuiRenderer` receives pixels rather than business snapshots. Input and frame deadlines share one select loop. There is no movement timer when nothing moves. Reconnection keeps the pure runtime and decoded cache but creates fresh native objects and last-frame state. Missed exposures are skipped arithmetically, never replayed. GUI failure retains deduplicated needs-input/ready notifications.
- **User configuration is merged.** The installer chooses inline `config.toml` hooks when the existing config has event matcher groups; Codex's `hooks.state` metadata alone does not select inline mode. Otherwise it uses `hooks.json`. It records its choice and created entries in `~/.config/codex-pet/install.json` so uninstall can remove its own hooks. Back up any changed user file and preserve unrelated hooks and settings.

## Overlay and touch details

The production default remains PNG. The internal shared transport uses one
framebuffer for the lifetime of one connection, `ARGB888` on the wire and
premultiplied RGBA bytes in memory. Pillow premultiplication uses the same
32 MiB cache budget as base/derived/PNG frames. The verified version-7 dispatch
response to `getVersion` fences staging consumption after blit/refresh; it does
not fence Android screen presentation. Unknown plugin versions are rejected on
the shared path. Size changes retire the entire connection before allocating
another buffer. A shared failure closes both channels, mmap and FD, then the GUI
worker opens a new PNG connection and remembers the failure for its lifetime.
This includes failed event reads and movement writes, even for a static frame
with no pending animation deadline.
There is no active-connection `deleteBuffer`. Android ashmem capacity is queried
with `ASHMEM_GET_SIZE`; regular shared files use `fstat`. Repeated ancillary copies
from Android LocalSocket are discarded after adopting the first descriptor.
`tools/probe_production_renderer.py` exercises the actual renderer for three
canvases; native-resource and human acceptance still gate default rollout.

`renderer.policy.RendererPolicy` chooses from backend version and frame canvas,
without examining pet IDs or business states. Its rollout gate is currently
closed. An injected acceptance policy permits only binding 0.1.6, plugin 7 and
256×256; unknown versions and other canvases keep PNG. A transport change retires
the old connection even when it was PNG. The worker publishes immutable
`RendererStatus` independently of the window, retaining the latest connection
error and sticky fallback reason after recovery. IPC/ordinary CLI read that
snapshot without importing image or GUI modules into the CLI process.

`TermuxGuiRenderer` keeps one 64 dp `ImageView` in one native overlay. There are no text cards, menus or secondary product overlays. `codex-pet pet list` exposes the catalog; `pet use <id>` persists selection and wakes the running daemon. Frames carry independent width/height and packed immutable straight RGBA8 in sRGB. Pillow rejects unknown profiles before composition; it does not silently treat RGBA conversion as ICC conversion. PNG is premultiplied by Android decoding; shared bytes are explicitly premultiplied before copying. Native positions are screen pixels; moves only occur during drag.

Termux:GUI emits an overlay-wide touch event with absolute screen coordinates for every touch in the overlay window. Use it as the drag gesture source so recognition does not depend on the ordering of events from separate paths. A tap has no action; dragging can start anywhere on the 64 dp icon after 6 dp of movement. The saved starting position plus the screen-coordinate delta keeps the original grab point under the finger. The targeted View touch event is optional and only refines the grab anchor near screen edges; its nested `pointers` report source-image pixels, so scale those coordinates to the 64 dp view before applying them. Releasing saves the new position; a cancelled gesture restores its start. `TermuxGuiRenderer.input()` normalizes and scopes native events, using measured view width and height independently. `DragController` owns gesture state without native APIs or files; `GuiWorker` applies moves and persists only committed releases. An early targeted anchor is retained until overlay down. Cancel, screen-off, and connection loss restore the last committed position; secondary pointer transitions are ignored. A tap never changes the logical position.

The installed binding expects a normal activity tuple, while an overlay returns an integer ID; `_overlay()` contains this compatibility detail. The inspected version has no overlay reply for `getConfiguration`. Layout calibration instead waits up to 1.5 seconds for valid `getDimensions`, measuring both axes independently. All native operations have bounded reads; no dimension query occurs on each frame. Check the installed binding source before relying on new APIs.

## Verification by change area

| Change | Evidence before completion |
| --- | --- |
| Session or event mapping | Add a focused state/parser test; cover missing JSON fields, official priority, turn ordering, Ready persistence through late activity hooks, missing turn IDs, and SessionEnd as applicable; run the full suite |
| IPC, startup, or hooks | Exercise concurrent start/stale socket or config preservation in isolated fixtures; confirm the hook helper returns promptly on failure; run the full suite |
| Animation playback | Assert physical frame references, exact exposure boundaries, transitions, holds and long skips through `PetRuntime`/`ClipTimeline`; compare offline compiled schedules and independent baseline pixels |
| GUI layout, art, or touch | Add an icon-only binding or touch regression test; run the full suite; on a Termux device run `bash ./install.sh` to deploy and restart, then run `codex-pet status` and `codex-pet test`; inspect the log and verify the actual gesture or state visually |
| Install or uninstall | Test against temporary user configuration, including existing unrelated hooks and repeated install/remove; use the real device only for the final smoke check |

Current automated tests under `tests/` cover playback schedules, GUI touch, native binding calls, and GUI reconnection. Add state, IPC, or installer tests when changing those paths. For a visual frame review, run `python tools/preview_animation.py --state ready --cycles 2` and open the generated `~/.cache/codex-pet/preview-ready.html` in a browser. The preview uses the shared playback schedule and production PNG frames in a 192 CSS px container; the actual 64 dp size must be checked on the device. It helps spot abrupt poses but does not emulate Termux:GUI's native ImageView or Android rendering. For uninstalled artwork, `--candidate manifest.json` uses explicit file paths and exposure durations as described in the [acceptance guide](animation-acceptance.md); it does not apply production composition or change runtime assets. `codex-pet test` cycles through states but cannot prove a physical touch gesture; record whether that was checked by a person. Android overlay permission must be granted in Termux:GUI by the user.

For a live diagnostic, `codex-pet status` shows process and GUI health. From this checkout, `python -c 'from codex_pet.runtime import request; print(request({"action": "status"})["overlay"])'` also shows logical position and touch count. `codex-pet test` checks displayed states most strictly when it is the only session; another active session can win the priority selection, so end or isolate other sessions before judging the visual sequence. When temporarily isolating the current active session, retain its turn ID and restore it in `finally`; a status snapshot is not a lossless backup of all sessions or their lifecycle metadata. Do not restore another session from just the aggregate state.

For screenshot-free visual and motion checks, run `python tools/audit_animation.py --state ready --cycles 2` or `python tools/audit_animation.py --state running --cycles 2`. It renders production FrameSource/FrameComposer pixels with premultiplied bilinear sampling at the 64 dp overlay size (3× density by default), writes a labeled contact sheet plus individual frames, and records frame hashes, delays, transition pixel changes, tail movement, chest stability, and (for running) all four paw paths relative to an orange hip anchor in `audit.json`. The running contact sheet marks near and far hind paws in magenta and cyan, and near and far forepaws in green and orange. Coordinates come from the versioned artwork manifest. Its PASS checks visible landmark sampling; track ranges, separation and phase labels remain diagnostics and do not certify gait or aesthetics. Set `--density` to match another device. This checks the production frame pixels and schedule after display-size scaling; it does not claim to reproduce Android's exact image-filtering implementation.

The overlay keeps the same 64 dp viewport across states, so equal 256 px frame dimensions do not guarantee equal apparent mascot size. The [pet image and animation standards](animation-assets.md) route authoring work through model and scale calibration, pose and timing plans, reference-based generation, and acceptance. The [acceptance guide](animation-acceptance.md) distinguishes the existing tools' production-frame checks from candidate review and device evidence; their current paw coordinates and motion thresholds apply to specific existing artwork.

For gait rationale, pose planning, and paw-track audit workflow, see [the dog gait animation guide](animation-gait.md).

## Compiled pet packs

The Akita Running cycle retains physical order 00,08,01,02,03,04,09,05,06,07
and 40/40/80/80/80/40/40/80/80/80 ms exposures (640 ms total). Same-pet
Running→Ready enters ready/05→06→07 at 120 ms each, then the ordinary happy-hop
entry and rest loop. Other origins enter the hop directly. The rest loop never
replays the turn or airborne poses; its blink is a static exported face-only
composite. Blocked holds its final pose. Robot timing remains unchanged.

Original file/pixel acceptance remains under `docs/artwork/akita/`: the
`accepted-baseline.json`, `2026-10-local-motion/`, `2026-10-collar/`,
`2026-10-continuity/` and `current-running.json` records describe the accepted
drawings and paw annotations. Rejected sixteen-frame sources remain in
`2026-10-gallop/`. The derived blink recipe and pixel fingerprint are in
`2026-10-pack/`; no new drawing or gait acceptance is implied by this refactor.

`assets/<id>/pet.json` owns frame references, independent canvas/display dimensions, clips, roles, transitions and count decorations. `pet_pack.py` validates paths, budgets, durations and finite next chains. Builtin execution is restricted to `robot_v1`. Akita references unchanged physical PNGs and an exported, pixel-identical face-only blink with recorded provenance.

V1 deliberately supports only `display_dp: [64,64]`; other display declarations
fail preflight instead of being ignored. Canvas width/height remain independent
from that display size. Clip durations must fit a signed 64-bit nanosecond range.
`image_contract.py` centralizes per-image RGBA allocation checks for packs,
codec, frame values and mmap buffers, without image or native GUI imports.

`PetRuntime` selects clip entries from visible activity. `ClipTimeline` uses integer nanosecond cumulative ends, binary search and arithmetic loop skipping; it never replays missed frames. Static/final holds have no deadline. Running→Ready entry applies only within the same pack; new activity interrupts immediately, and only Running reacts to count changes. Both live and offline schedules consume compiled clips; production tools load physical frame references through FrameSource/FrameComposer. Historical artwork exports and existing regression fixtures retain computed integer labels in `tools/historical_animation.py`; those labels are derived from the compiled clips and contain no authored playback tables.

Deployment validates both staged manifests and decodes their referenced images before replacing `current`; the private release contains all required assets. Invalid assets preserve the previous installation.

Compatibility inventory: the old `codex_pet.art` and `codex_pet.animation` modules are removed from the deployed package. `tools/historical_art.py` retains export names needed by archived experiments and original artwork fingerprint tests; it delegates pixels to the production codec/pipeline. `tools/historical_animation.py` computes historical numeric labels from compiled clips for existing preview/audit reports and archive regression fixtures. It contains no authored timings or appearance-specific playback branches. These helpers are not installed with the runtime; archived experiment JSON and artwork acceptance files remain unchanged.

The image codec imports Pillow lazily, validates dimensions before allocation and rejects unsupported profiles. The installer exercises a known partially transparent PNG and decodes the staged pack before activation. Missing Pillow or its PNG decoder preserves the prior release. Hook/status/catalog entrypoints are tested without image or native GUI imports. `tests/png_fingerprint.py` is a test-only frozen serializer for archived hashes; no legacy codec ABI remains in the runtime.

## Managed frame memory

The GUI owner shares one `FrameCache` across decoded pixels, count composition and the selected transport encoding. Its 32 MiB budget counts immutable byte values, not total Python/Android RSS. Derived frames and old encodings are evicted before decoded originals; zero/insufficient capacity still renders through bounded temporary values. Individual image inputs/decoded payloads are capped at 64 MiB. Robot and badges draw directly into RGBA without PNG round trips. Keys include pack revision/reference and bounded count. Close discards PNG/premultiplied encoding; reusable source pixels survive reconnect. PNG deduplication advances after successful send; shared deduplication advances after the consumption fence.

`python tools/probe_frame_cache.py --output /tmp/cache.json` measures cold preparation, switches, variant pressure, managed bytes and Python-visible RSS in a fresh process. It does not measure the Android GUI process or power.

## Deployment and end-to-end acceptance

`tests/test_install_entrypoint.py` runs the real `install.sh`, stable wrappers,
hook stdin, Unix IPC, daemon/worker, compiled frames and native binding. Only
Android's external broadcast endpoint is replaced by a separate protocol peer
that records decoded pixels and window moves. Test homes/prefixes are temporary;
faults do not alter real user configuration. Repeated install, unavailable
checkout, invalid pack/activation target, failed restart after stopping the old
daemon, current/previous restoration, explicit rollback and uninstall are
checked with actual processes/files. The native peer is not an Android rendering
or resource-leak certificate.

Shared rollout still requires production human checks and independent Android
window/buffer cleanup observations. Stable local FD/map counts alone are
insufficient. Keep #13/#14/#15 open while their mandatory device gates remain
unobserved, even when all software checks pass.
