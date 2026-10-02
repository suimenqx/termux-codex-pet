# Implementation review

Review baseline: `c7edbfa125e20599d1ae3500f822201e4aba8cfc`.
Reviewed implementation snapshot: `5eff128eee4eade49b1b7f6dd5779a28cde5b09c`.
The two independent reviewers used the repository agreements and parent #1 /
tickets #2–#15, respectively. Both subsequently inspected the working-tree
resolutions and reported no remaining concern in those fixes. They did not run
the final suite; execution evidence is recorded in
[implementation-status.md](implementation-status.md).

## Standards

No documented-standard violation was identified. Two low-priority design
judgments were reported:

- `touch.py` represented the drag start with an anonymous six-element tuple,
  including unused original-position fields. The resolution introduces a named
  immutable pointer/origin value; existing gesture behavior stays covered by
  the same input/output tests.
- The per-image 64 MiB allocation rule was repeated in pack validation, codec
  and frame validation. `image_contract.py` now owns dimension/byte checks and
  the fixed v1 display size without loading image or native dependencies. The
  aggregate pack budget remains a separately named policy.

Current animation guides also referenced the removed runtime art/playback
facades. Those links now identify the compiled manifest, frame pipeline and
runtime; archived artwork evidence remains unchanged.

## Spec

Two P2 behavior defects were identified and corrected:

- The required sticky shared-to-PNG recovery only covered frame submission.
  Event-channel EOF or a failed movement write could reopen shared repeatedly.
  A closed shared connection now records the same failure and opens a fresh PNG
  connection regardless of which native operation detected it. A static Robot
  regression isolates event/move failure from animation deadlines. The real APK
  recovery probe additionally checks event EOF, main EOF and consumption timeout.
- The pack accepted arbitrary `display_dp` while the view always used 64×64 dp.
  V1 now rejects unsupported dimensions during preflight. This preserves the
  specification's existing display size instead of silently ignoring metadata.

The reviewer also noted that an enormous integer duration could compile and
later overflow deadline conversion. Clip totals now have an explicit signed
64-bit nanosecond limit and an invalid-manifest regression.

Required native Android window/buffer observations and longer background /
reconnection checks remain incomplete. Human production shared acceptance was
reported as normal, but that does not prove native resource cleanup. The user
explicitly chose to retain PNG default without a USB debugging host. Parent #1
and tickets #13–#15 therefore remain open; default shared rollout is not claimed.

Totals: Standards 0 hard violations, 2 design findings resolved; Spec 2 P2 defects
resolved plus 1 duration edge case resolved. The remaining Spec gap is the
explicitly deferred device acceptance gate, not a passed test.
