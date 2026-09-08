# Assigned test-phase evidence

Target: `d0866aa569c25bf3a5a0d70e27b3ee68a0501544`.
No source or test files were changed. Temporary worktree files were removed.

- `lane-selection.txt`: real CLI enumeration of six nonempty, disjoint serial shards covering all 152 paths, plus stale-count and out-of-range refusals. Workflow YAML was parsed semantically to confirm a six-member matrix and unchanged 20-minute cap.
- `measurements-check.txt`: comparison of the live CLI partition and the published duration table with maxima from four downloaded green source runs. These are historical measurements, not fresh full-suite timings. Replays of the original five-shard artifacts correctly fail the new balance guard.
- `guard-healthy.txt` and `live-healthy.json`: a fresh, filtered numbered shard completed normally and passed the guard, reporting partial 1 of 6 coverage and the 20-minute bound.
- `live-paused.txt`, `live-paused.json`, and `guard-paused.txt`: the actual runner process group was paused for 1082 seconds after its first script began, then resumed. Its unchanged clock and artifact writer recorded 1083605 ms (18.06 min). Both selected scripts completed successfully. The guard exited 1 before the 20-minute cap, reported 90.3%, and named the script whose measured duration exceeded its hint.
- `input-refusals.txt`: actual CLI refusals for no input and a missing file, both exit 2.
- `runner-contract.log`: the existing focused runner suite passed, including its synthetic recorded-wall-time-versus-script-sum case. These unit/fixture checks are supplemental and are not claimed as live scenarios.

The live runs use the public family exclusions to select two existing scripts from `portable-serial-5of6`. They exercise the real runner and its freshly produced artifacts without mocking timing data or changing the implementation. They do not claim complete six-shard performance on GitHub runners. Full CI execution is reserved for the outer executor by this phase's authority boundary.

`live-guard-driver.py` and `measurements-check.py` record the exact evidence-producing procedures.
