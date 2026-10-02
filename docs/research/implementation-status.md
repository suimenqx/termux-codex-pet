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
