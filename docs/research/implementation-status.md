# Refactor implementation evidence

Review baseline: `c7edbfa125e20599d1ae3500f822201e4aba8cfc`. Scope: GitHub #1, tickets #2–#15.

Baseline: 153 tests passed on the device (78.239 s). The five untracked recordings are user files and are excluded from changes.

## P0 — implemented and deployed

- #2: real held startup lock reproduced a timeout beyond a 1 s watchdog with a 50 ms requested budget. Fixed with an absolute deadline; real hook failure and released-lock/existing-daemon tests pass.
- #3: bounded local transport covers handshake, protocol framing, EOF, partial/invalid messages, peer UID and received FD ownership. Real socket boundary tests pass.
- #4: 20,000 wake notifications reproduced a 3 s watchdog timeout; nonblocking wake and immutable overlay status replace the blocked path.

Validation: full suite 163 tests passed (79.760 s); after adding the concurrent-start case, all four real startup-boundary tests passed. GUI suite: 26 tests passed. Mypy 1.18.2 checked the four changed runtime/GUI/transport/daemon modules without errors; latest mypy required a native build that failed on this device, so the pure Python checker is isolated in the development venv. Diff check passed.

Deployment: private release 20261002T212744Z-7ae73e44, plugin version 7, daemon PID 26593. An isolated full device demonstration completed Idle → Running → Needs input → Ready → Blocked and returned to Idle with zero sessions and GUI ready. The current owned Codex session was restored with its turn ID afterwards. No new GUI error log entries. PNG transport remains active; physical gestures are reserved for the dedicated production gesture ticket.

P1–P5 are still in progress; no overall completion claim.

## P1a — semantic event migration

#5 separates Codex/legacy IPC normalization from the session model. Added entrypoint regression for hook-independent turn_end/activity and malformed event fields. State (7), hook/config (5), daemon (10) and targeted type checks (7 modules) pass. Device installation and isolated state demonstration pass; full suite 166 tests passed (150.868 s).

## P1b frame boundary — implemented

#6 moves native window operations into TermuxGuiRenderer. PetRuntime selects FrameRequest; FrameSource/FrameComposer return immutable packed RGBA. Native rendering no longer receives a business snapshot. Old codec and artwork helpers remain temporary compatibility code until their own tickets.

Frame-pipeline and artwork (14) tests pass, GUI tests (25) pass, eight affected modules pass mypy, and the deployed isolated full-state device demonstration returns to zero sessions with GUI ready. Production transport remains PNG. Full suite: 167 tests passed (140.031 s).

## T06 / #7 — input and gesture ownership

Native event normalization now produces immutable `TouchInput`; a pure `DragController` handles anchors, 6 dp slop, cancellation and commits. The GUI owner performs movement and persistence. Non-square source and measured view axes scale independently; measurement has a 1.5 second budget. Screen-off and targeted cancellation restore the saved position.

Validation: full suite 169 tests passed (150.031 s); two additional focused cancellation/screen-off cases passed with all 16 touch tests. Targeted type checks passed. Deployed release `20261002T214948Z-7d8f47f7`; isolated five-state device smoke returned idle with zero sessions and GUI ready. Production tap, edge drag, secondary-finger and screen-off gestures are pending the requested human check; earlier probe acceptance does not substitute for this.

## T07 / #8 — Robot compiled pack

Robot now uses a data-only manifest and a validated builtin whitelist. Live playback and offline Robot schedules share compiled clips; integer nanoseconds and arithmetic loop skipping replace elapsed-frame catch-up for Robot. Installation validates the staged manifest before activation; invalid packs leave the active release intact. PNG decode allocation is capped at 64 MiB.

Validation: 540 Robot paths match the pre-refactor pixel/exposure fingerprints in `tests/fixtures/playback-baseline.json`. Exact deadlines, static holds, invalid manifests and 1 h/24 h/large resume checks pass. Full suite: 175 tests passed (90.298 s), plus the newly added independent baseline regression passed. Six affected modules pass mypy. Release `20261002T215908Z-e51f2c5f`, PID 6785, passed separate isolated Akita and Robot state demonstrations; Robot was restored to the prior Akita selection afterwards. No new GUI errors. Akita compatibility remains for the next ticket.

## T08 / #9 — complete Akita pack

Both pets now use PetRuntime and the compiled integer timeline. Akita's transitions, loop entries and final holds are manifest data; physical assets retain their original bytes. The old face-only blink is exported once, with its source rectangle and PNG/RGBA fingerprints in `docs/artwork/akita/2026-10-pack/`. Offline timing now consumes the same compiled schedule; temporary historical indices are the next migration target.

Validation: all 1080 baseline paths / 8694 exposures match decoded RGBA and duration. Additional exact-boundary, count reset, interruption, cross-pet, 1 h/24 h and static-hold checks pass. Missing/corrupt derived assets are rejected before activation. Exported blink reproduces byte-for-byte. All original artwork fingerprints remain asserted; the two file-set checks now explicitly include the recorded derived file. Final full suite: 179 tests passed (100.888 s); GUI: 29 passed; five affected modules pass mypy. Resume observations are recorded in `docs/experiments/2026-10-renderer/compiled-timeline.json` and are not timing guarantees.

Deployed release `20261002T220332Z-085d6799`, PID 11854, passed the isolated full-state demonstration with zero remaining sessions and GUI ready. No new GUI errors. New production visual/gesture acceptance remains pending human observation.

### Production gesture feedback

2026-10-02: after deploying the production input/drag path, the user replied “基本都是正常的。” to the requested tap/small motion, edge dragging and persistence, secondary-finger, and drag-during-screen-off checks. No specific abnormal behavior was reported. This feedback applies to the PNG production path; shared transport has not yet been accepted.

## T09 / #10 — offline tools share production frames

Preview and audit now use compiled physical references plus FrameSource/FrameComposer, with `--pet`, `--count`, source-state transitions and finite cycles. Audit retains Akita paw annotations, image fingerprints, candidate workflows and visual-review caveats. Authored playback tables and the linear catch-up algorithm are removed. Historical integer labels are computed from clips for archived artwork scripts and their regression fixtures; the compatibility inventory is documented in architecture.md. Existing experiment and artwork evidence was not rewritten.

Validation: actual preview/audit subprocess entrypoints pass for both pets, badges, transitions and holds; preview pixels match live runtime requests across all visible states. Existing audit tests (8), playback tests (16) and artwork checks pass. The CLI-entry regression caught a formatter moving imports above path setup; imports were corrected and retested through the commands. Final full suite: 181 tests passed (109.561 s). Whole-package mypy: 25 modules pass. Isolated device demonstration on release `20261002T221113Z-59adb111` returned zero sessions and GUI ready; logs remain clean. User production gesture feedback is recorded above.

## T10 / #11 — Pillow codec and dependency preflight

The runtime now has one lazy Pillow codec; the handwritten libpng ctypes ABI is removed. The frame and pack contracts explicitly identify straight RGBA8 / sRGB. Unsupported ICC/HDR/gamma/chromaticity, invalid dimensions and over-budget images are rejected. install.sh installs `python-pillow` and exercises real PNG decoding before deployment; staged packs are decoded before activation. No NumPy runtime dependency was added.

Actual package installation added Pillow 12.3.0 and four required libraries without upgrades/removals. Real subprocess deployment with no Pillow (`python -S`) and with the PNG decoder removed both retained the active release and user files. Hook, status and catalog were exercised through their entrypoints without Pillow/GUI/NumPy imports. All 1080 pixel/exposure paths and 65,536 premultiplication color/alpha pairs pass. Historical exports now compare RGBA; original asset file hashes are still asserted. A test-only frozen PNG serializer validates archived hashes whose original compression differs from Pillow.

Validation: full suite 186 passed (128.775 s), whole-package mypy 25 modules pass, artwork/motion/audit checks pass. Release `20261002T222238Z-56d696c2`, PID 18714, passed the isolated full-state device demonstration. Two fresh production PNG renderer connections rendered both pets and badges successfully; observations and concurrent-load limitation are recorded in `pillow-production.json`. A reconnect request while GUI was healthy was a no-op, so it is not counted as a fault-recovery test. First preparation and repeated encode/decode work remain the next cache ticket's target.

## T11 / #12 — shared byte budget and direct RGBA preparation

One 32 MiB GUI-owned cache now covers decoded pixels, derived badges and PNG encoding. Pure whitelisted drawing functions replace Robot and badge PNG round trips. Base pixels have retention priority, count variants are bounded, and zero/small-budget rendering remains correct after eviction. Failed presents retry correctly; close removes encoding and a fresh renderer presents again. Offline tools share a cache too; historical art facades are outside the production import path.

Validation: all 1080 baseline paths still match; zero/512 KiB/32 MiB paths pass. GUI tests: 30; full suite: 189 passed (103.655 s); whole-package mypy: 27 modules. Serial fresh-process observations in `cache-production.json`: 1011 preparations, maximum managed payload 33,554,425 bytes under a 33,554,432 byte budget, 558 evictions, Python-visible peak RSS 62,148 KiB and 28,116 KiB after cache clear. Cold idle 87.349 ms, first badged Running 24.914 ms, repeat hits 0.042/0.027 ms; these are device observations, not latency guarantees or total native memory.

Deployed release `20261002T223338Z-edb9220c`, PID 23982; isolated full-state demonstration and logs pass. Production remains PNG.

## T12 / #13 — shared ownership and fresh PNG recovery

The internal shared renderer now owns exactly one framebuffer per connection,
prepares cached Pillow RGBa bytes, blits and refreshes, and waits for the verified
APK-7 consumption response before advancing its last-frame key. Dimensions
changes retire the connection; shared failure is sticky within the worker and
recovers through a fresh PNG connection. Production default is still PNG.

Actual production-path probing exposed two details absent from regular-file
fixtures: Android LocalSocket re-attaches the same outbound descriptor to each
header/body write, and Android 12 ashmem is a character device with zero stat
size. The transport now adopts the first ancillary handle and lets plain recv
discard subsequent copies. Multiple handles in the first ancillary message
remain invalid. The buffer checks ashmem capacity via ioctl before mmap.

Five renderer tests exercise real socketpairs/shared-file FDs, premultiplied
pixels, duplicate frames, unknown APK versions, EOF/timeout, allocation and
read-only mmap failures, canvas changes, idempotent close and worker recovery.
Protocol regressions also cover repeated Android descriptor delivery. The
production renderer completed two alternating rounds for 64×64, 256×256 and
384×416. Every case returned local FD count to 4 and ashmem maps to 0 after close;
shared live state held one map. `shared-production.json` records raw samples;
last cases overlapped the full suite, so performance needs a serial rerun before
rollout. These local observations do not establish native cleanup.

Native-resource acceptance is pending a wireless ADB connection. The installed
adb executable works when its per-command LD_LIBRARY_PATH selects Termux's own
libraries; the inherited Codex library path had shadowed libc++. No global
environment was changed. Ordinary Termux cannot inspect the plugin's proc files
or Android windows. The user has been asked for wireless pairing details; no
native no-leak or default-rollout claim is made while this remains unobserved.

Full suite: 195 tests passed (97.558 s); whole-package mypy: 28 modules.
Release `20261002T225618Z-b00703ff`, PID 4085, passed the isolated five-state
device demonstration with PNG, returned to zero sessions, and logged no new GUI
errors. This is an implementation checkpoint; #13 remains open for the required
Android-side resource observation, and #14 remains gated.

## T13 / #14 — diagnostics and gated capability selection

The backend policy now selects by actual binding/plugin version and canvas,
without pet IDs or business state. Its normal rollout gate remains closed.
An internal acceptance injection permits 256×256 with binding 0.1.6 / plugin 7;
64×64, other canvases and unknown versions remain PNG. Policy changes retire the
entire prior connection. Status/logs publish immutable version, transport,
selection reason, remembered fallback and latest connection error snapshots.

Full suite: 198 tests passed (97.434 s); whole-package mypy: 29 modules. Tests
cover unknown capability conservatism, PNG-to-shared rebuilding, and diagnosis
after shared timeout/fresh PNG recovery. Release `20261002T230150Z-07a245ec`
reported the expected normal PNG policy. `tools/probe_shared_daemon.py` then ran
that installed production daemon with the internal shared capability injection;
PID 5833 reported shared and passed the isolated five-state demonstration with
zero remaining sessions and no connection errors. The tool preserves the normal
release policy and restores normal startup after its finite acceptance window.

Shared production edges/gestures/lock/rotation/background human verification has
been requested during that window. Native Android resource observation is still
pending ADB pairing. No default rollout approval or completion of #14 is claimed.

### Production human feedback and recovery evidence

The user replied **“正常。”** to the shared production check covering dark/light
edges, tap/slop, edge anchor, multi-touch, drag during lock/unlock, rotation and
another foreground app. This is separate from the earlier simplified probe and
the PNG feedback. The five-minute controlled window ended normally and restored
the ordinary PNG daemon (PID 7445). It does not establish long-duration background
stability or native allocation cleanup.

`shared-production-serial.json` repeats the comparison without concurrent test
work: two alternating rounds, 16 warmup exposures and 60 samples per case,
80 ms deadlines. Changed Akita 256×256 sample medians were PNG 6.231/14.700 ms
versus shared 1.904/2.768 ms including the consumption response; they are not
screen latency. Robot has only three changed samples per case because its
original 2-second exposures are preserved, so no Robot performance conclusion
is drawn. Each case returned to four local FDs and zero ashmem mappings.

`shared-recovery.json` runs the real worker and APK with one controlled missing
fence reply (the known overlay configuration no-reply path) and one local EOF
injection. Both opened exactly one fresh PNG connection, published the cause,
and returned local resources to baseline on stop. These tests do not establish
Android-side cleanup.

The user reports their Mate 60 Pro+ has no wireless-debugging entry. Huawei's
[official explanation](https://consumer.huawei.com/en/support/content/en-us15997564/)
confirms this limitation and suggests USB debugging. A computer/data-cable path
has been requested; no pairing credentials were collected. Native window/buffer
observations and longer background/reconnect pressure remain unfulfilled gates.

The user subsequently confirmed **“目前没有，先保留 PNG 默认”** (no available
computer; keep PNG as default for now). Normal deployment therefore retains the
closed rollout gate. USB setup is not a user installation dependency. Shared
native-resource acceptance/default rollout is explicitly deferred, not passed.

## T14 / #15 — real deployment and pipeline checks

The actual shell install/uninstall entrypoints now run in isolated temporary
source/home/prefix fixtures. The only platform substitute is an external Android
broadcast executable that speaks real Termux:GUI socket messages and records
decoded PNG pixels and moves. A separate executable fault stops the old daemon
then fails the new restart; the installer restores both runtime links, exact
hooks/preferences, and a working prior daemon. Repeated installation, moving the
checkout, invalid activation target/pack, explicit rollback, foreign command
restoration and uninstall pass. Real hook stdin→Adapter→Unix IPC→SessionStore→
PetRuntime/compiler/source/composer→native-wire recording covers visible poses,
late turns, input bounds/fail-open, one daemon and persisted drag position.

The deployed package no longer contains old art/playback facades or unused
catalog geometry/profile dispatch. Historical labels/export names live only in
`tools/historical_*.py` for archived reproduction and original image tests; they
delegate to the current codec/pipeline and compiled clips. Original artwork
and archived result files are preserved. Final full-suite/review/deploy evidence
follows; #15 cannot close before the upstream native-resource gates pass.

Final software check before independent review: 201 tests passed (115.393 s),
27 production modules passed mypy, and diff whitespace checks passed. The first
full run found a historical export script still importing the removed facade;
all four archived script imports were migrated, its reproduction test passed,
and the full suite was rerun successfully. Release
`20261002T231632Z-b8080171`, PID 11883, passed isolated status/state demonstration
and recent-log checks with normal PNG policy. The source cleanup preserves all
asset bytes; historical helper modules are excluded from the installed release.

## Independent review and final software validation

The [two-axis review](implementation-review.md) found two specification defects:
event/move connection failure did not remember shared fallback, and unsupported
display dimensions were accepted then ignored. Both are fixed. The static-frame
protocol regression verifies event EOF and a failed movement descriptor recover
on exactly one fresh PNG connection. The test retains a duplicate main descriptor
while delivering touches so server teardown cannot race event injection; it also
waits for the peer to receive PNG rather than treating asynchronous send completion
as receipt. Unsupported display sizes and enormous clip durations fail preflight.
Named drag-start data and one lightweight image allocation contract resolve the
two standards design findings without changing production gestures.

`shared-recovery-reviewed.json` exercises consumption timeout, main EOF and event
EOF using the real worker, binding and APK. Event EOF follows a successful static
shared frame, with no animation deadline to hide the event recovery path. All
three cases establish exactly two connections and recover to PNG; after stop,
each has four local FDs and zero ashmem mappings. The original two-case evidence
is preserved. Android-side allocation cleanup remains unobserved.

Final affected suites passed: shared renderer (6), compiled playback (6), touch
(16), and Pillow contract (5). Full `unittest discover` passed **202 tests in
114.260 s**. Mypy 1.18.2 checked **28 production modules** with
`--ignore-missing-imports` because the third-party binding has no type stubs;
this is not a claim that the binding itself was typechecked. `git diff --check`
passed. Both independent reviewers inspected the fixes without new findings.

Deployed release **`20261002T233539Z-b09de64a`**, PID **22643**, passed installer
checks, status, isolated five-state `codex-pet test`, and recent-log inspection.
GUI is ready, actual transport is PNG, and saved position **942,229** is preserved.
No additional gesture acceptance is claimed for this deployment: existing human
PNG/shared feedback plus unchanged-behavior gesture regressions are recorded
above. The required native and longer stress gates remain deferred by the user's
decision; #13–#15 and parent #1 remain open.

## Follow-up: lossless WebP atlas

The user's atlas question was checked against all 35 current production frames
in an offline probe. Exact lossless WebP is 1,581,300 bytes versus 3,117,602 bytes
of individual PNGs, with identical RGBA after slicing and an independent hidden
RGB / all-alpha-values check. This experiment changes no production assets or
transport policy. [Results and concrete integration points](lossless-atlas-followup.md)
describe the source/compiler/codec/preflight work and distinguish compressed
size, decoded payload and runtime memory. Full AtlasFrameSource migration remains
optional follow-up work, outside parent #1's implementation scope.
