# Turn-end beacon-age test validation

Result: GO for the assigned test phase. No source changes were needed.

Target: c4c2314ae98784915d0cffa7b60fdfc487e5fc29
Base: 40c50ea8843c5b6a5351db8352675537252b653e
Platform: macOS, with native BSD timestamp tools.

## Intended protection and measured cause

Outside away mode, a 600-second poll interval must not extend the ordinary
300-second watcher-beacon grace. With the same valid watcher owner, a fresh
beacon allows a turn to end, a 400-second beacon blocks, and refreshing only
the beacon allows again.

The base fixture had a daemon lock and no watcher lock. Both a 0-second and a
400-second beacon returned exit 2. Removing watcher beacon-age rejection still
left the old test green. Missing watcher ownership masked the intended test.
These historical-fixture and mutation checks are focused behavioral tests,
not live watcher sessions.

## Executable counterfactual proof

| Test version / injected regression | Observed result |
| --- | --- |
| Base test, original product | Pass |
| Base test, watcher age rejection removed | Pass: demonstrates original defect |
| Repaired test, watcher age rejection removed | Fails: expected exit 2, got 0 |
| Repaired test, normal grace incorrectly widened to 660 seconds | Fails: expected exit 2, got 0 |
| Repaired test, watcher ownership omitted | Fresh control fails: expected exit 0, got 2 |
| Repaired test, original product restored | Pass: hook exits 0, 2, 0 |

The two deliberately broken product copies were exercised before the final
green repaired-test execution. No tracked production file was mutated.
Six nearby watcher-ownership and away-mode grace cases also passed.
The initial trace capture emitted a descriptor warning; the evidence driver
was corrected and the complete focused matrix rerun cleanly.

## Real running product

Registered a real custom watcher check through bin/fm-check-register.sh and
started bin/fm-watch.sh in an isolated home inside the submitted worktree.
The check executed and wrote its expected local side effect; the watcher
published its own PID, identity, home, watcher path, and beacon.
No agent, terminal backend, or watcher process was mocked in this run.

Called the actual bin/fm-turnend-guard.sh executable with a Stop payload,
FM_POLL=600, unset/default FM_GUARD_GRACE, and away mode off:

- Fresh product-generated beacon: exit 0, no output.
- Same watcher, beacon aged to 400 seconds: exit 2 and recovery instruction.
- Same watcher, only beacon refreshed: exit 0, no output.
- Fresh beacon, ownership lock temporarily hidden: exit 2.
- Same ownership restored: exit 0, no output.

Age was controlled by changing the beacon's persisted mtime; this did not wait
400 real seconds. The real process remained running with the same identity.
The transcript records each payload, measured age, exit, and emitted banner.
The watcher was explicitly stopped after verification; its final sleep SIGTERM
line in real-watcher.log is cleanup, not a product failure.
No vendor-agent session or rendered UI was involved in this CLI/test change.

## Reproduction and evidence

Run from the submitted worktree:

```sh
python3 /Users/mremond/.no-mistakes/evidence/01M22GJM13BYHFAZ319P7Z0YVF/verify-turnend.py matrix
python3 /Users/mremond/.no-mistakes/evidence/01M22GJM13BYHFAZ319P7Z0YVF/verify-turnend.py live
```

- mutation-matrix.log and mutation-matrix.json: baseline, injected failures, final green.
- target-pristine.trace.log: executed fresh_status=0, status=2, restored_status=0.
- live-guard-transcript.log and live-guard-results.json: actual product output and ownership proof.
- validation-context.json: target tree, source hashes, host, clean final worktree.

All transient product copies and homes were removed. Evidence remains only in
this evidence directory. No full repository suite, linter, formatter, static
analysis, publication, or other pipeline phase was run.
