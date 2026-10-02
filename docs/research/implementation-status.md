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
