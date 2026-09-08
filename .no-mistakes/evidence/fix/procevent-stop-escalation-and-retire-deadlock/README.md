# Process-event stop validation

Target: `46e578847c6a8ce11c18b2d48e5b6ffdb7d9d930` against base `b84e0e362face25f3dd8945297a3df1320d7668c`.
Host: macOS / Darwin 25.5.0 arm64.

Both original defects were reproduced through the real executable, using the same registered blocking-command workload on base and target.
The old guard caused the permanent form of the leak: it killed the only leader that could prove ownership, abandoned the child, and was therefore worse than no guard.
The base survivor continued working after TERM (tick log grew from 21 to 38).
The repaired guard stopped the same command and all group members.

The base healthy runner needed KILL: public `start` returned 137 and retirement took 5.429 seconds on this host.
The target returned 143 (TERM) in 0.487 seconds.
Healthy reconciliation and home sweep also returned TERM status 143.
Signals, rather than elapsed-time calibration, establish the deadlock fix.

Target retirement also succeeded after an absent leader, a real Darwin zombie (`Z`, `<defunct>`), and an actual loss of the `ps` executable from a private PATH after TERM.
The same unreadable identity was refused before proof, as were a stale readable claim and a live process that did not lead its group.
One failed owner-lease check followed by recovery left the runner unsignalled; a separate live home was preserved while an expired home was reaped.

The residue remains: when a runner is killed externally, its blocking child survives and the source silently stops listening.
The guard, retire, reconcile, and sweep-home all refused that group; the retained claim prevented replacement.
This delivery does not resolve that permanently refused group.
The Lavish adapter's signal traps were not changed or tested for deletion.

## Evidence

- `live-cli-transcript.log`: base/target commands, returned CLI output, signal statuses, process-group snapshots, and continuing/ceased work.
- `extra-transcript.log`: real missing-executable identity failures, nonleader refusal, and single-miss lease recovery.
- `guard-clock-transcript.log`: corrected lease-clock measurement; with the shortened 2-second lease and 1-second check, the group disappeared 10.107 seconds after the last lease refresh on this loaded host. This is an observation, not a hard real-time guarantee.
- `validation-observations.json`: consolidated results, correction notice, and cleanup verification.
- `focused-identity-regressions.log`: four existing executable-interface regressions selected from `tests/fm-procevent.test.sh`; these use ps shims and are supplementary, not live proof.
- `target-*-state.json`: captured product-owned registry and claim state.

The initial timing run mixed Python's default monotonic clock with the product's CLOCK_MONOTONIC timestamp. Its negative lease-age value and associated bound assertion are invalid. The corrected guard run above supersedes that timing assertion; the raw initial log is retained for transparency.

Linux execution remains untested: the running Docker daemon is Linux, but neither locally cached image contains the required Perl runtime (one also lacks Bash). No packages or images were installed. A ready image with Bash, Perl and procps would allow the same executable scenarios to run there.

## Commands used

The base executable tree was materialized within this worktree with `git archive b84e0e362face25f3dd8945297a3df1320d7668c bin | tar -x -C .procevent-validation/baseline`.
The main driver was `python3 <evidence>/live-procevent.py`, followed by `guard-clock` and `extra` modes.
The focused existing regression block was copied with its original helpers into a temporary file under tests and run with `TMPDIR="$PWD/.procevent-validation/tmp" bash tests/.fm-procevent-focused-validation.sh`.
The evidence copy is `focused-identity-regressions.sh`; it expects to run under `tests/` with the existing `tests/lib.sh`.
All runtime homes, private PATH links, baseline files and the temporary test selector were removed after verifying that no test-owned runners or poll commands remained.
No source changes, linters, complete repository suite, pipeline-control commands, pushes, PR operations or CI phases were performed.
