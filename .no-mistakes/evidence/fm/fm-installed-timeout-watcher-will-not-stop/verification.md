# Watcher shutdown test-phase evidence

Target: `d1272be552cd29ce58a82b02f83237ff81d370b5`.
Tree: `1b0243c42efc4006d4b3bfd927332d4c4c3bcc6f`.
Base: `40c50ea8843c5b6a5351db8352675537252b653e`.
Host: macOS, uid 501 (non-root); no `timeout` or `gtimeout` installed.

## Live product results

The actual target `bin/fm-watch.sh`, `bin/fm-check-register.sh`, and lock primitive ran with isolated homes inside the assigned worktree. These runs used real processes, signals, permissions, and persisted state; they did not substitute watcher or lock behavior.

- Normal TERM: exit 1 after 0.948 seconds, downtime marker published, singleton released, empty stderr.
- Foreign process owns recovery-marker lock: TERM exit 1 after 5.451 seconds; stderr named the holder and the five-second deadline. The holder stayed alive and owned its lock. Stale singleton evidence remained. After the holder was killed, a new watcher exited 0 with `check: rearm-resurface`.
- Unwritable state: mode 0555 genuinely prevented owner-directory creation under uid 501. The real primitive returned 1 in 0.146 seconds. The signalled watcher exited 1 after 4.464 seconds and emitted the five-second deadline message, retaining its singleton evidence. Bash's integer `SECONDS` explains a measured interval below five seconds.
- Abandoned steal: a command interceptor performed the real primary-lock unlink, then stopped the real stealer before replacement. Killing that process left an absent primary and `.steal` owned by the dead stealer. The next real primitive call acquired successfully, and a subsequent watcher emitted `check: rearm-resurface` and exited 0.
- Real fallback timeout: registered a custom check which returned while a TERM-ignoring Perl descendant existed. The watcher drained the child, then exited 1 in 0.535 seconds after TERM; no sentinel or private check snapshot remained.

See `live-transcript.txt`, including exact commands, PIDs, process observations, emitted messages, and persisted marker contents.

## Counterfactual and diagnostic evidence

`resource-mutation-transcript.txt`: in a separate runtime copy, reverted resource-error distinction and early return. Under the same permission fault, acquisition remained running after six seconds and the signalled watcher exceeded the unchanged twenty-second ceiling. Both mutant processes were killed. The target source was never edited.

`diagnostic-live.err`: a separate runtime copy deliberately refused TERM at BOTH handler sites and retained the check's orphan for diagnostic observation. The unchanged assertion emitted elapsed time, exactly 150 polls, process state and wchan, a three-level descendant tree, the recorded child whose PPID was 1, and the stderr tail. It exited 1 with the stuck-watcher message.

`diagnostic-unknown.err`: the same controlled failure, with a silent ps injected into the test caller, instead exited 1 with the separate unreadable-liveness message. UNKNOWN was never accepted as successful shutdown. These are fault-injected checks; they do not reproduce the unexplained original CI failure or constitute unmodified live-product proof of that failure.

## Focused existing regressions

Temporary runners loaded the original test definitions and invoked only these selectors; no tracked test was moved, repacked, or reordered. The security cases ran with errexit enabled. All selectors passed.

- `tests/fm-test-fixtures.test.sh`: `test_is_live_non_zombie_separates_gone_from_unreadable` (real live process, zombie with bounded readiness, departed PID, and silent-ps injection).
- `tests/fm-watcher-lock.test.sh`: `test_shutdown_is_bounded_when_marker_lock_is_held`, `test_lock_resource_failure_returns`, `test_shutdown_is_bounded_when_state_is_unwritable`, `test_lock_steals_dead_pid_lock`, `test_lock_live_steal_mutex_is_not_reclaimed`, `test_lock_empty_pid_uses_minimum_grace`, `test_lock_paused_mid_acquire_claim_fails_during_steal`.
- `tests/fm-pr-check-security.test.sh`: `test_custom_snapshot_cleanup_on_signal`, `test_returned_custom_check_descendants_are_drained`. Its installed-timeout case supplies its own timeout shim, so that result is fixture coverage, not proof with an installed timeout binary.
- `tests/fm-wake-queue.test.sh`: `test_self_held_lock_reclaims_instead_of_deadlocking`.
- `tests/fm-watch-arm.test.sh`: `test_marker_publish_failure_retains_recovery_evidence`.
- `tests/fm-daemon.test.sh`: `test_wedge_alarm_backgrounded_command_times_out_and_reaps_descendant`.

Exact evidence-producing commands, executed from the assigned worktree:

```
python3 /Users/mremond/.no-mistakes/evidence/01M22Z7YQYD4K70MWCSC6FV3P4/drive_watchers.py live
python3 /Users/mremond/.no-mistakes/evidence/01M22Z7YQYD4K70MWCSC6FV3P4/drive_watchers.py targeted
python3 /Users/mremond/.no-mistakes/evidence/01M22Z7YQYD4K70MWCSC6FV3P4/drive_watchers.py resource-mutation
python3 /Users/mremond/.no-mistakes/evidence/01M22Z7YQYD4K70MWCSC6FV3P4/diagnostics.py
python3 /Users/mremond/.no-mistakes/evidence/01M22Z7YQYD4K70MWCSC6FV3P4/adjacent.py
```

## Limits and cleanup

The original CI cause remains unestablished. An installed-timeout live run needs a real timeout/gtimeout binary on the test PATH; this phase did not install system packages or rerun CI. Diagnostic and unreadable-ps branches were demonstrated through controlled faults, not an organically failing CI runner. No full suite, lint, formatter, static analysis, publication, or pipeline-control phase ran.

Temporary runners, isolated homes, runtime copies, and generated data were removed. A detached process from the deliberately broken diagnostic runtime was identified by its exact run-local path and killed before cleanup. Tracked source and tests are unchanged; final git status is clean. Evidence remains in this directory.

A delivery whose subject is a watcher that cannot STOP nearly shipped a watcher that cannot START, and the review caught it. The killed-stealer experiment above proves the reviewed startup correction works.
