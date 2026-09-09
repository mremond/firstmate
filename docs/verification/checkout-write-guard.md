# Checkout write guarantee: verification

Active evidence for the guarantee owned by [`../fm-checkout-write-guard.md`](../fm-checkout-write-guard.md) and enforced by `bin/fm-test-run.sh`.
The regression that keeps this current is `tests/fm-checkout-write-guard.test.sh`; run it with `bin/fm-test-run.sh tests/fm-checkout-write-guard.test.sh`.

## The guarantee can fail

A check that only agrees with itself proves nothing, so the primary evidence is a mutation pair rather than a green run.

- Date: 2026-09-09
- Host: Darwin 25.5.0, arm64
- Command: `bin/fm-test-run.sh tests/fm-checkout-write-guard.test.sh`

The regression drives twelve cases through the guard's and the runner's command lines, each a mutation pair.
The decisive one runs the same fixture test script twice under `bin/fm-test-run.sh`, differing by one line:

```
# with `mkdir -p state` in the fixture
not ok - tests/fm-leaky-fixture.test.sh wrote into the repository checkout
FM_CHECKOUT_WRITE fm-leaky-fixture.test.sh created ./state
FM_TEST_SUMMARY total=1 failed=1

# same fixture, that one line removed
FM_TEST_SUMMARY total=1 failed=0
```

The other pairs pin the cases a weaker implementation would miss: a write inside an already-present gitignored directory, a removal, a rewrite of an untracked file, an edit of a tracked file, a pin that tolerates one script's recorded paths and nothing else, an allowance that tolerates only the paths it names, `.git` churn that is deliberately not a violation, the guarded command's own exit status surviving, the opt-out announcing itself, the runner refusing to start once the guard script is deleted, and the concurrent phase below.

## The concurrent phase carries its scripts' pins

A concurrent phase is guarded as a unit, because workers share one checkout and a write cannot be attributed to the script that made it.
The first implementation of that unit consulted no pins, which made every pinned script a hard failure the moment the runner scheduled it concurrently - and the runner does that by default, without `--jobs`, whenever a selection holds more than one admissible script.

Measured 2026-09-09 on Darwin 25.5.0 arm64, with `state/` absent, running two really pinned scripts:

```
$ bin/fm-test-run.sh --jobs 2 tests/fm-pending-reply.test.sh tests/fm-procevent.test.sh
FM_CHECKOUT_WRITE concurrent-phase created ./state
fm-test-run: a script in the concurrent phase wrote into the repository checkout; rerun serially to attribute it
exit 1
```

Both scripts are pinned for exactly `./state`, and `--jobs 1` accepts the same run as recorded debt, so the refusal was spurious: it reported debt the guard had already accepted, and its advice to rerun serially was the only way to get a green run.
A guard that refuses correct work gets switched off, which would have cost the whole guarantee.

The phase now passes the pin of every script admitted to it. It tolerates nothing that is not already recorded debt.
`tests/fm-checkout-write-guard.test.sh` pins both directions, deriving its fixtures from the live pin table rather than naming a row:

```
ok - a concurrent phase carries its scripts' pins and still refuses a path none of them names
```

That case is itself mutation-proven. With the pin union removed from `bin/fm-test-run.sh` and nothing else changed:

```
not ok - no concurrent phase reported the pinned write as recorded debt (missing: 'FM_CHECKOUT_WRITE_PINNED concurrent-phase created ./state')
FM_TEST_SUMMARY total=1 failed=1
```

and with it restored, `FM_TEST_SUMMARY total=1 failed=0`.
The case asserts the `concurrent-phase` marker rather than only an exit status, so it cannot pass by quietly never running concurrently.

## The guarantee and the delivered fixture repair compose

The three `test_spawn_refuses_*` cases in `tests/fm-backend.test.sh` clear every `FM_*_OVERRIDE` to exercise default home resolution, and that is exactly what makes them write `state/` into the checkout.
Measured on a pristine clone at `40c50ea8`, with `state/` absent, guarded:

| checkout state | result |
|---|---|
| `40c50ea8` alone | the file aborts at the symlinked-prefix case before reaching the refusal cases, creates nothing, and the guard is silent |
| `40c50ea8` + PR #4056 | all 27 test functions pass, and the guard refuses: `FM_CHECKOUT_WRITE fm-backend.test.sh created ./state` |
| `40c50ea8` + PR #4056 + the change on this branch | all 27 pass, the guard is silent, and `state/` is never created |

So the fixture repair and the guarantee only compose once the three refusal cases name a home of their own.

## Which pitfall option was chosen, and why the other was not

Both candidates were run rather than reasoned about.
The measurement that decides it is the file's own asserted outcomes: 28 `ok -` lines, compared line by line between the unmodified file (run with `state/` present, since it cannot complete without it) and the modified file (run with `state/` absent).

**Both halves require PR #4056 applied, and the comparison does not reproduce without it.**
That precondition is not a detail: on this branch alone the file aborts at the symlinked-prefix case, which is the defect #4056 repairs, long before reaching the cases this change touches.
Re-measured 2026-09-09 on Darwin 25.5.0 arm64, without #4056, the modified file with `state/` absent yields 20 `ok -` lines and `not ok - fm-spawn.sh should succeed for a project reached through a symlinked prefix`, not 28.
Applying only #4056's `tests/fm-backend.test.sh` diff onto this branch composes cleanly and restores the intended comparison:

```
$ diff baseline.ok-lines optionA.ok-lines   # no output: identical
$ wc -l baseline.ok-lines optionA.ok-lines
      28 baseline.ok-lines
      28 optionA.ok-lines
```

Under the guard, that same modified run with `state/` absent reports no violation and leaves no `state/` behind.

- **Chosen - name a temporary `FM_HOME`, leave every `FM_*_OVERRIDE` cleared.** `FM_HOME` is not one of the test hooks those cases clear; it is the ordinary production selector for a home's `state/`, `data/`, `config/` and `projects/`, while scripts still come from the tracked code root. The cases therefore keep exercising default resolution, the assertions are byte-identical, and the side effect lands in a temporary directory.
- **Rejected - run the cases from a copied checkout.** A copy without `.git` is not a git repository (`git rev-parse --show-toplevel` in the copy: `fatal: not a git repository`), and `bin/fm-spawn.sh` invokes git in 27 places, so the copy quietly changes the subject under test. Copying `.git` as well is worse here: this repository's checkout is a linked worktree whose `.git` is a pointer file into the primary repository, so a faithful copy means copying the primary repository (28 MB) and running fixtures against it. The copy also only relocates the write - `state/` still appears, inside the copy - where naming a home removes it.

## Pin inventory

Rows are recorded in `pin_table` in `bin/fm-checkout-write-guard.sh`.
Rebuild them with the loop in [`../fm-checkout-write-guard.md`](../fm-checkout-write-guard.md#rebuilding-the-pin-table).

- Date: 2026-09-09
- Host: Darwin 25.5.0, arm64, loaded (load average 28-47 throughout, so several scripts ran far slower than their recorded hints)
- Method: 149 of the 192 test scripts, each run alone from a pristine `git clone` of `40c50ea8`, inventoried before and after, and the clone restored between scripts so every script was measured from the same starting point rather than from its predecessor's debris.
- Not measured: the 13 `real-herdr-gated` scripts and three further Herdr-driving portable scripts, because this task carried no Herdr lab contract and must not drive Herdr lifecycle behaviour; and the `live-harness-optin` family, which needs credentials this host does not hold.

**Result: 22 scripts write into the checkout, and they write exactly two things.**

Twenty-one create `state/`, all for one reason: they drive a Firstmate script with the home unset or cleared, and `bin/fm-wake-lib.sh` creates `"$FM_HOME/state"` at source time, which then resolves to the checkout.

The twenty-second is different and is the reason a measured table beats a reasoned one: `tests/fm-voice-relay.test.sh` runs `bin/*.py` from the checkout, and the interpreter writes `bin/__pycache__/*.pyc` beside the source. That is a write into `bin/`, not into a gitignored home directory, and no reading of the `state/` mechanism would have predicted it.

Nine of the twenty-two were not in the earlier census, which had measured 62 scripts and concentrated on those driving `fm-spawn.sh` or `fm-teardown.sh`: `fm-pending-reply`, `fm-procevent`, `fm-procevent-quota`, `fm-send-inbox`, `fm-send-remote-delivery`, `fm-send-resolve-key`, `fm-send-secondmate-marker`, `fm-startup-memory-budget`, and `fm-voice-relay`.

Two rows are carried from that census rather than from this sweep. `tests/fm-control-relaunch.test.sh` failed part-way here, so its result is a lower bound, and `tests/fm-watch-triage.test.sh` is the known intermittent case - it created the directory in one of three earlier runs and in none of this one.

### Limits of this measurement

- 19 of the 149 scripts did not complete on this host (16 failed, three hit the 600s bound). A script that stops early never reaches its own leak, so each of those results is a lower bound, not a measurement. The pins carried from the census cover the two of them already known to leak.
- The sixteen Herdr rows are pinned without measurement. They are the largest piece of unearned tolerance in the table and the first thing to re-measure from a task that holds the Herdr lab contract.
- A leak that only appears on Linux, or only with credentials, is outside what this host could see at all.

