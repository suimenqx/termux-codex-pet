# Architecture and change map

This is the reference for agents changing hook ingestion, sessions, IPC, daemon lifecycle, native overlay layout or touch, and install/uninstall behavior. Read the relevant section, then inspect the owning code and its tests; code remains authoritative for exact values.

The [measured refactor plan](research/termux-gui-refactor-plan.md) records the investigation baseline and migration gates. [Implementation evidence](research/implementation-status.md) records what has shipped and which device gates remain open. The contracts below describe the current implementation.

## Event path and ownership

```text
Codex lifecycle hook JSON on stdin
  → bin/codex-pet-event → hook.event_main → adapters.codex.event_from_hook
  → runtime.send_event → delivery.EventJournal atomic inbox + events.sock wake
  → runtime.request over ~/.cache/codex-pet/pet.sock (receipt)
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
| Durable delivery | `codex_pet/delivery.py` | Atomic inbox, state checkpoint and replay receipts in the private runtime cache |
| Notification delivery | `codex_pet/notifications.py` | One bounded worker, latest pending notification and removal of stale fallback notices |
| Session model | `codex_pet/state.py` | Semantic event application, session priority, turn ordering, counts |
| CLI process ownership | `codex_pet/processes.py` | Boot/PID/start-time identity, bounded ancestor discovery, verified kernel exit descriptors |
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

Community source conversion is an offline boundary in `tools/pet_import/`.
`build_recipe()` owns hash-locked acquisition, fixed layout, pixel deduplication,
validated pack publication and provenance; format decoders handle PNG sequences,
composed GIFs, a documented eSheep XML subset, VP9 alpha and a restricted Spine3.8
Canvas export. `community_pets/*.json` owns character/source/state choices.
`tools/import_pets.py` exposes this boundary; the earlier five-pack importer
shares its pack writer with unchanged outputs. Optional ffmpeg and Node/Canvas
stay outside installed releases and daemon imports. No source-specific runtime,
renderer, IPC or touch branches are added. See [recipe maintenance](../community_pets/README.md).

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
- **One daemon.** `daemon.lock` prevents duplicates; `start.lock` serializes simultaneous hook starts. The daemon removes stale IPC/wake sockets before bind and removes its owned sockets on shutdown. Requests and replies are one newline-terminated JSON object, capped at 64 KiB. IPC actions are `event`, `status`, `reconnect`, `set_appearance`, and `stop`. GUI outage notifications are deduplicated by state/project/message across the GUI and IPC threads; the key is reserved and nonblocking work is queued while holding the state lock. One separate notification worker invokes Android commands without blocking IPC, coalesces pending notices to the latest state, and removes stale notices on resolution or GUI recovery.
- **Session state follows observed lifecycle signals.** `SessionStore` keeps sessions, ended-session timestamps and retired turn IDs. Local aggregation is needs input, blocked, unknown, running, ready, idle: one stopped turn never obscures another session's work. A turn start resets approvals; pending approvals are counted by a hash of canonical tool name/input with human descriptions excluded. Matching completions resolve one request, unrelated completions preserve the remainder, duplicate tool IDs cannot consume another request, and early completions are retained to match delayed same-turn requests. Different tools' activities are not globally ordered against one another. Boot-scoped monotonic source times fence terminal events, new turns and session lifecycle evidence without depending on wall-clock corrections; repeated startup cannot reset active work. Completed turns reject late activity. Known different IDs require a new prompt; missing IDs cannot finish a known active turn and instead mark evidence uncertain. Manual demonstration events remain supported. Restored evidence is unknown until a newer event confirms it; replayed checkpoint evidence cannot confirm freshness. There is no time-based inference of idle or failure. Ready means observed Stop, not success; Needs input means unresolved observed approval request, not confirmed open UI; its confidence is requested and the frame carries a question-mark marker. Blocked remains explicit/demo only. Hooks do not identify text-only questions or final turn outcomes.
- **Events outlive their sender.** The hook normalizes once, publishes a private atomic/fsynced inbox file, sends a nonblocking datagram wake, then attempts bounded IPC/start/retry with the same ID and source timestamp. The daemon binds the wake socket before startup replay and includes it in its event-driven select loop. It commits sessions and receipts before removing inbox files. Pending I/O failures retain events, show unknown and retry once per second; batches with remaining work drain without a polling delay. IPC `ok` acknowledges durable processing, while `applied` separately reports whether evidence changed state. Ordinary status drains retained work too. A startup-lock timeout leaves an event for the next successful start; the hook never waits indefinitely. Disk publication failure is logged/fail-open and cannot promise durability. State, inbox and receipts stay under `~/.cache/codex-pet/`; preferences stay under `~/.config/codex-pet/`.

- **Session and process are separate identities.** CLI hook entry captures the nearest Codex client in at most 32 same-process ancestry steps, skipping its local app-server. It uses only PID, `/proc` start ticks and boot identity; command-line data is used transiently to identify app-server mode and is never persisted. A process token is stable across its hooks and changes on PID reuse or reboot. The store isolates `(session_id, instance_id)` entries, including turn fences and approvals. SessionEnd removes only the emitter's entry for that thread; unqualified lifecycle hooks cannot change qualified entries. Manual/legacy events retain their old unqualified key and are marked legacy. A recovered format-1 checkpoint migrates only on matching newer evidence; earlier-boot approval data is not adopted.

- **Process death is lifecycle evidence.** One `ProcessWatcher` owns a kernel pidfd per identified client, shared across its session entries. Before and after opening, boot/start ticks fence PID recycling; descriptor readability indicates process exit. Python's public pidfd wrapper is preferred; Termux uses the typed Android libc `pidfd_open` symbol when Python omits it. No syscall number is guessed. Descriptors join the daemon's existing select loop, with no activity timeout or process polling timer. Confirmed death publishes a durable `instance_end` event with a stable receipt ID before deleting that client's entries. Closed process tokens are checkpointed and reject later hooks after restart. Normal SessionEnd releases unused descriptors without sealing the whole still-live process. An orphaned app-server cannot become a fresh client. Unverifiable identity or unavailable exit monitoring explicitly renders Unknown; descriptors are retired on disappearance, identity changes, process exit and daemon shutdown. Restored live processes are watched again, while their business evidence stays recovered until a fresh hook.

- **Counters declare their scope.** `session_count` counts distinct thread IDs; `instance_count` counts distinct process tokens (legacy keys stand in for unidentified sources); `entry_count` counts session/process pairs. Activity counts and global `pending_approvals` cover all pairs. `selected_pending_approvals` refers only to the displayed pair. Status includes PID/session/state/confidence/approval rows, at most 32 rows and 32 KiB, explicitly flagging truncation while keeping global totals complete. State demonstrations use entry count when deciding whether their state owns the overlay. Installation's smoke start/end use the same hook/owner path so the temporary entry is removed.

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

The Akita Running cycle uses physical order 00–19 with repeated 42/42/41 ms
exposures (834 ms total). Same-pet Running→Ready enters ready/05→06→07 at
120 ms each, then the ordinary happy-hop entry and rest loop. Other origins enter
the hop directly. The rest loop never replays the turn or airborne poses; its
blink is a static exported face-only composite. Blocked holds its final pose.
Robot timing remains unchanged. The current production hashes and running audit
markers are recorded in `docs/artwork/akita/2026-10-grok-v2/delivery.json` and
`docs/artwork/akita/current-running.json`; the 3D reference packet is separate
from runtime assets.

`assets/<id>/pet.json` owns frame references, independent canvas/display dimensions, clips, roles, transitions and count decorations. `pet_pack.py` validates paths, budgets, durations and finite next chains. Builtin execution is restricted to `robot_v1`. Akita references unchanged physical PNGs and an exported, pixel-identical face-only blink with recorded provenance.

V1 deliberately supports only `display_dp: [64,64]`; other display declarations
fail preflight instead of being ignored. Canvas width/height remain independent
from that display size. Clip durations must fit a signed 64-bit nanosecond range.
`image_contract.py` centralizes per-image RGBA allocation checks for packs,
codec, frame values and mmap buffers, without image or native GUI imports.

`PetRuntime` selects clip entries from visible activity. `ClipTimeline` uses integer nanosecond cumulative ends, binary search and arithmetic loop skipping; it never replays missed frames. Static/final holds have no deadline. Running→Ready entry applies only within the same pack; new activity interrupts immediately, and only Running reacts to count changes. Both live and offline schedules consume compiled clips; production tools load physical frame references through FrameSource/FrameComposer. Offline compatibility helpers retain the existing import names used by preview and audit tools; their labels are derived from the compiled clips and contain no separate authored playback tables.

Deployment validates both staged manifests and decodes their referenced images before replacing `current`; the private release contains all required assets. Invalid assets preserve the previous installation.

Compatibility inventory: the old `codex_pet.art` and `codex_pet.animation` modules are removed from the deployed package. `tools/historical_art.py` and `tools/historical_animation.py` retain stable offline-tool import names while delegating to the production codec and compiled clips. They are not installed with the runtime and contain no appearance-specific playback branches.

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

## State submission diagnostics

Every processed unique event advances a revision. GUI refresh receives an immutable snapshot with that revision, the source timestamp and monotonic ingestion time. After a successful native image submission (including an unchanged-image deduplication), it publishes immutable `SubmittedStatus`: revision, event ID, displayed aggregate state, submission time, ingestion-to-submission and source-to-submission milliseconds. A failed presentation cannot advance it; connection teardown clears it. IPC compares processed and submitted revisions without accessing native objects. Per-revision logs omit tool arguments and user messages. These observations use monotonic clocks within one device boot and end at native command submission, not Android presentation. Earlier-boot evidence remains recovered/unknown, and source latency is unavailable without a matching boot identity.

Unknown uses the pack's idle frame/clip; hook approval requests retain the attention pose. Both carry a neutral question-mark decoration keyed separately in the existing byte cache. No production sprite or motion timing is replaced. The same 64 dp window and touch path remain in use.

The [2026-10-04 device evidence](experiments/2026-10-state-integrity/device-results.json) records an isolated five-state demonstration and 19 controlled hook updates through the installed helper and production PNG/native submission path. All submitted revisions matched processed revisions, including missing-ID Unknown and fresh-evidence recovery. Helper launch to native submission measured 239.6 ms median and 312.2 ms maximum in this finite sample; these measurements do not cover Codex dispatch or Android screen presentation. The new question-mark badge still needs human visual acceptance. Existing physical touch acceptance is unchanged; this verification did not repeat gestures.

The [multi-instance device evidence](experiments/2026-10-multi-instances/device-results.json) records controlled CLI producer processes using the installed hook helper and production PNG overlay. Two processes sharing a thread kept independent approvals and scoped SessionEnd. Killing a waiting process committed its exit in 47.3 ms in this observation, with no hook or IPC wake; its late replay was rejected. Eight concurrent producers shared one daemon, and owned pidfds returned from 9 to the original 1 after cleanup. The isolated five-state demonstration passed and the original session, turn and process identity were preserved. These are process/IPC/native-submission checks without model calls, Android screen-presentation timing or repeated physical gestures; the isolated real-process regression also verifies closed-owner replay rejection after daemon restart.
