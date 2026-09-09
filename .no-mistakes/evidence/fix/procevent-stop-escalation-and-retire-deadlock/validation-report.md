# Stop-path test evidence

Validated `7d00287b5e8145ac6e72f6de21015fdf01fab7ae` (tree `83a3ff3ccfafba85152424ad1dfbedc253b0f0b7`) against `40c50ea8843c5b6a5351db8352675537252b653e`.
All final product scenarios passed. No tracked files were changed.

## Real running product

These runs used the actual `fm-procevent.sh` executable, isolated homes and claim roots, and actual OS process groups. Perl source processes installed real TERM handlers and spawned real descendants; process inspection and signalling were not mocked. The permission-failure cases ran in an existing Linux container with init and networking disabled; all other rows ran on Darwin 25.5.0.

| User action or adversarial input | Observed result | Raw evidence |
| --- | --- | --- |
| Retire a healthy attached source | Base attached start exited **137 (KILL)**; target exited **143 (TERM)**. Target retirement took 5.136 seconds, returned `retired: live-healthy`, and left no group. Exit status, not duration, determines the verdict. | [base](live-base.log), [target](live-healthy-final.log) |
| Retire a TERM-resistant source | The leader disappeared while both child processes remained; both logged TERM; escalation removed the group and retirement returned success. | [retirement](live-target.log) |
| Retire while the leader becomes a real macOS zombie | `ps` recorded leader 74006 as `Z <defunct>` with children 93069 and 93676 still alive; both received TERM; retirement then removed the group. | [zombie](live-zombie-final.log) |
| Stop refreshing the owning home's lease | With a 5-second lease and 1-second checks, the resistant group disappeared after **14.016 seconds** on the loaded host, inside the 22-second regression allowance. | [owner loss](live-target-ready.log) |
| Kill the leader independently, then retire/reconcile/sweep | Retire and sweep refused; reconcile returned `started=0 stopped=0 uncertain=1`; claim and registration stayed intact; the guard was observed exiting without signalling the surviving children. | [unproved group](live-cold-guard-final.log) |
| Supply a live mismatched identity or a real nonleader PID in the persisted claim | Both first-signal attempts refused, kept retry state, and sent no TERM. | [identity and nonleader](live-target.log) |
| Make the actual private ps binary nonexecutable before TERM | Kernel execution failed with EACCES. Retirement refused and preserved the group, claim and registration. | [actual inspection failure](live-linux-ps-failure.log) |
| Make that same binary nonexecutable only when the source receives TERM | The leader was held alive with SIGSTOP after the startup boundary. TERM produced a real EACCES condition; escalation killed the proved group and removed its claim and registration. | [actual inspection failure](live-linux-ps-failure.log) |

[Structured process snapshots, CLI argv/output and results](scenario-results.json) retain the exact records behind these observations. [The driver](live-stop-driver.py) is included for replay.

## Regression strength

The selected guard section of `tests/fm-procevent.test.sh` was executed unchanged, with its original timing assertion, in the existing `fmlab:latest` image (`b3a51436ba08`) using real init. Only the extraction boilerplate and test-owned cleanup trap were added.

- Target: passed.
- Base: failed because the group remained at the 16-second deadline.
- Target with only the `proved` argument removed from escalation: failed at that same deadline.
- Target with 40 seconds inserted before the guard stop: failed at that same deadline.

[Guard evidence](guard-mutations.txt) and [exact container commands](linux-guard-runs.json).
The base reproduction changes only `fm-procevent.sh` and `fm-procevent-lib.sh` back to the specified base; dependencies are from the checked-out target. These are the only runtime files changed by this branch.

The four existing inspection fixtures also passed on macOS: mismatch, unreadable identity after TERM, unreadable PGID after TERM, and nonleader. Those fixture probes use ps shims; they are supplemental regression evidence, separate from the real permission-failure runs above. [Focused output](inspection-regression.log).

For the fixture's startup race, a disposable code copy delays source-lock release by three seconds after launching the child. Removing the fixture's public `list` barrier leaves the leader stopped in state T and retirement waiting after seven seconds, with no TERM received. Restoring the barrier lets all four cases complete. [Blocked fixture](startup-without-barrier.log), [four corrected cases](startup-barrier-delayed.log).

## Scope and complete test-step accounting

The actual `--help` output and exit status match the base. The script header and `.agents/skills/` satisfy their explicit byte-identical contracts. [Byte-contract evidence](unchanged-interface.txt).

The initial subject-file command was `TMPDIR="$PWD/.test-stop-validation/tmp" bin/fm-test-run.sh tests/fm-procevent.test.sh --jobs 1 --per-script-timeout-secs 900`. It was deliberately interrupted under high host load after 340 seconds while still in unrelated cases and replaced by the focused checks above; its exit 143 is not a product failure. [Partial subject run](procevent-regression.log).

Early driver attempts exposed setup problems: newline argv rejection, leases expiring before startup, a missed zombie observation window, incomplete private PATH utilities, and a copied macOS ps exiting 137. Those attempts are retained in the raw logs and itemized in `scenario-results.json`; each affected product scenario was re-driven successfully after correcting setup. No runtime product failure remains.

No complete repository suite, linter, formatter, static analysis, publication, PR or CI phase was run. There is no UI surface in this change; CLI transcripts and process state are the reviewer-visible evidence. Temporary source copies, toolsets, homes and test processes are removed after evidence capture.
