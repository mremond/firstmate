# The checkout write guarantee

A test may not create, remove, or modify any path under the repository checkout it runs from.

`bin/fm-checkout-write-guard.sh` owns that prohibition, the pinned pre-existing exceptions, and the mechanics.
`bin/fm-test-run.sh` is its single enforcement point: a serial run guards each script by itself, a concurrent run guards the phase as a unit, and a violation is a failed script.
This page owns why the guarantee exists and what it is worth, so the reasoning survives an edit that removes the enforcement.

## What it is for

Test scripts are assumed isolated from each other by temporary directories, ports, and process boundaries.
The repository checkout is the one piece of shared state none of those cover.
It is a single mutable directory every script runs from, and anything a script leaves behind there is visible to every script that follows it.

That is not hypothetical.
An assertion in `tests/fm-backend.test.sh` about symlinked project prefixes passed if and only if a gitignored `state/` directory existed inside the checkout - deterministic in both directions, measured alone in a single process, unrelated to parallelism, contention, or load.
Any test script that drives a Firstmate script with the home unset creates that directory as a side effect, because `bin/fm-wake-lib.sh` creates `"$FM_HOME/state"` at source time and an unset home resolves to the checkout; the measured list is in [`verification/checkout-write-guard.md`](verification/checkout-write-guard.md).
Whether one of those scripts had run, and got far enough, decided the assertion's verdict.
The test reported which neighbour had run first and presented the answer as a fact about symlinked prefixes.

The same channel explains the oldest complaint in software.
A developer's working copy silently grows that directory the first time they run the suite and never mentions it, so the case passes on the maintainer's machine and fails on a fresh runner.
Batch membership is derived rather than enumerated, so which scripts run before which changes whenever a test is added or a duration hint moves - and with it, silently, the verdict.

## What it must keep being

**A prohibition, not a report.**
A check that can only agree with itself is green forever and worth nothing.
`tests/fm-checkout-write-guard.test.sh` is written as mutation pairs for exactly that reason: every case runs the same fixture with a write and without it and requires the two verdicts to differ.
A change that makes those pairs agree has removed the guarantee even if the suite is still green.

**Loud when it is not running.**
`FM_CHECKOUT_WRITE_GUARD=off` disables the guard, and the guard then says so rather than passing quietly, because a silent pass is indistinguishable from a satisfied guarantee.
The escape hatch exists so a blocked caller edits one variable instead of deleting the enforcement.
`bin/fm-test-run.sh` refuses to execute at all when the guard script is missing, so removing it stops the suite instead of quietly dropping the guarantee.

**Debt that shrinks.**
Leaks that predate the guard are pinned one script at a time, each naming the exact paths that script may touch and why.
A pin is recorded debt, not an exemption: a pinned script writes only what its pin names, and an unpinned script writes nothing at all.
The correct way to clear a pin is to give that test a home of its own; widening the globs is not.
Never add a pin to make a newly written script pass.

## Known limits, stated rather than implied

- **A pinned leak can mask a new one.** If a pinned script creates `state/` earlier in the same lane, a later unpinned script creating the same path finds it already there and is not reported. Every pin removed shrinks that window, and it closes completely when the table is empty.
- **Concurrency loses attribution, not the pins.** Workers share one checkout, so a concurrent phase is guarded as a unit and names the phase rather than the script; rerunning serially attributes it.
That unit carries the pins of every script admitted to the phase, because a script writing exactly what its own pin records must not fail a run that merely happened to schedule it concurrently.
Without that, the ordinary default run of any selection containing a pinned script would go red on debt the guard has already accepted, and a guard that cries wolf gets switched off.
It tolerates nothing that is not already recorded debt: a path no admitted script is pinned for is still a violation.
- **`.git` is deliberately out of scope.** The subject is the working tree the next script reads. Branch and index safety in the primary checkout is owned by the runner's own placement refusal.
- **One residual blind spot.** A rewrite of an already-present untracked file that changes neither its size nor its modification time is not detected. Tracked files do not have that gap; their content is compared through git.
- **A few paths belong to the tooling, not to any test.** The validation pipeline writes its own evidence into the checkout while it is driving this very suite, and a file browser drops `.DS_Store` into a developer's copy. Those exact paths are structurally exempt and reported under their own marker rather than blamed on whichever script happened to be running. An exemption is not a pin: no test is expected to touch them, and nothing near them is covered.

## Rebuilding the pin table

The pins are measured, not guessed, and a stale table is worth re-measuring after a batch of test changes.
Measure against a disposable clone, never a live checkout, and restore the clone between scripts so each script is measured from the same starting point rather than from its predecessor's debris:

```sh
git clone --no-hardlinks <repo> /tmp/pin-sweep && cd /tmp/pin-sweep
for s in tests/*.test.sh; do
  bin/fm-checkout-write-guard.sh snapshot /tmp/before
  bash "$s" >/dev/null 2>&1
  bin/fm-checkout-write-guard.sh snapshot /tmp/after
  bin/fm-checkout-write-guard.sh compare /tmp/before /tmp/after --label "$(basename "$s")"
  git clean -qfdx && git checkout -q .
done
```

A script that aborts early never reaches its own leak, so a red script's result is a lower bound, not a measurement.
The dated result and the conditions it was taken under are recorded in [`verification/checkout-write-guard.md`](verification/checkout-write-guard.md).
