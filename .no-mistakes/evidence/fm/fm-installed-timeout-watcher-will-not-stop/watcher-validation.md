# Watcher validation on 31e4d35bec947717151b92359a2f04a542c05dd2

The real watcher and lock library ran in temporary homes inside the assigned worktree. No production file was changed.

## Fallback timeout: TERM after direct check returns

```json
{
  "scenario": "Fallback timeout: TERM after direct check returns",
  "result": "pass",
  "registration": "registered: state/custom.check.sh",
  "watcher_before": "65306 65247 65247 S    bash /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/bin/fm-watch.sh",
  "watcher_exit": 1,
  "term_to_exit_seconds": 0.088,
  "recorded_descendant_pid": 65960,
  "descendant_after": "absent",
  "sentinel_exists": false,
  "private_files_left": [],
  "singleton_lock_exists": false
}
```

## held-marker-new

```json
{
  "scenario": "held-marker-new",
  "result": "pass",
  "watcher_pid": 67012,
  "watcher_exit": 1,
  "term_to_exit_seconds": 5.06,
  "diagnostic": "watcher: recovery state could not be persisted within 5s (marker lock held by pid 67569); stopping and retaining stale lock evidence",
  "holder_process": "67569 65247 65247 S    bash -c . \"$1\"; fm_lock_try_acquire \"$2\" || exit 11; trap 'fm_lock_release \"$2\"; exit' TERM; echo ready > \"$3\"; while :; do sleep .1; done _ /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/bin/fm-wake-lib.sh /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/.nm-test-phase/live/held-marker-new/state/.watcher-down.lock /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/.nm-test-phase/live/held-marker-new/held-marker-new-holder.ready",
  "retained_watcher_lock_pid": "67012",
  "marker_before": "",
  "marker_after": ""
}
```

## held-marker-existing

```json
{
  "scenario": "held-marker-existing",
  "result": "pass",
  "watcher_pid": 70740,
  "watcher_exit": 1,
  "term_to_exit_seconds": 4.45,
  "diagnostic": "watcher: recovery state could not be persisted within 5s (marker lock held by pid 71323); stopping and retaining stale lock evidence",
  "holder_process": "71323 65247 65247 S    bash -c . \"$1\"; fm_lock_try_acquire \"$2\" || exit 11; trap 'fm_lock_release \"$2\"; exit' TERM; echo ready > \"$3\"; while :; do sleep .1; done _ /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/bin/fm-wake-lib.sh /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/.nm-test-phase/live/held-marker-existing/state/.watcher-down.lock /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/.nm-test-phase/live/held-marker-existing/held-marker-existing-holder.ready",
  "retained_watcher_lock_pid": "70740",
  "marker_before": "pending:downtime:71276.1789474056.g9lNGq",
  "marker_after": "pending:downtime:71276.1789474056.g9lNGq"
}
```

## Resource fault: genuine unwritable state

```json
{
  "scenario": "Resource fault: genuine unwritable state",
  "result": "pass",
  "uid": 501,
  "state_mode": "0555",
  "primitive_output": "acquisition_rc=1",
  "primitive_elapsed_seconds": 0.046,
  "watcher_exit": 1,
  "term_to_exit_seconds": 4.402,
  "diagnostic": "watcher: recovery state could not be persisted within 5s (marker lock held by pid unknown); stopping and retaining stale lock evidence",
  "retained_watcher_lock_pid": "74210"
}
```

## Ordinary publication ignores ambient timeout overrides

```json
{
  "scenario": "Ordinary publication ignores ambient timeout overrides",
  "result": "pass",
  "ambient_values": {
    "FM_RECOVERY_MARKER_LOCK_TIMEOUT": "1",
    "FM_WATCHER_SHUTDOWN_LOCK_SECS": "1"
  },
  "blocked_after_seconds": 6,
  "publication_exit": 0,
  "marker": "pending:downtime:83505.1789474072.IbEHBa",
  "elapsed_seconds": 6.456
}
```

## Stealer dies after removing primary lock; next acquirer and watcher start

```json
{
  "scenario": "Stealer dies after removing primary lock; next acquirer and watcher start",
  "result": "pass",
  "stopped_stealer": "83708 65247 65247 T    bash -c . \"$1\"\\012set -T\\012trap 'if [ \"$BASH_COMMAND\" = \"rc=1\" ] && [ \"${lockdir:-}\" = \"$STATE/.watch.lock\" ] && [ ! -e \"$STATE/.watch.lock\" ] && [ -e \"$STATE/.watch.lock.steal\" ]; then printf \"%s\\n\" \"${BASHPID:-$$}\" > \"$STATE/steal-gap\"; kill -STOP \"${BASHPID:-$$}\"; fi' DEBUG\\012fm_lock_try_acquire \"$STATE/.watch.lock\"\\012 _ /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/bin/fm-wake-lib.sh",
  "primary_absent_at_crash": true,
  "abandoned_steal_pid": "83708",
  "next_acquirer_output": "acquired_pid=83989\nrecovered_pid=",
  "next_acquirer_exit": 0,
  "steal_lock_reclaimed": true,
  "successor_watcher_pid": 84411,
  "successor_exit_after_term": 0,
  "successor_term_to_exit_seconds": 0.114
}
```

## Same process reclaims interrupted marker lock

```json
{
  "scenario": "Same process reclaims interrupted marker lock",
  "result": "pass",
  "exit": 0,
  "output": "marker=pending:downtime:85253.1789474074.f5o8ns\nreacquired_and_released"
}
```

## Recovery wake cleanup also times out and preserves the announced episode

```json
{
  "scenario": "Recovery wake cleanup also times out and preserves the announced episode",
  "result": "pass",
  "wake_output": "check: rearm-resurface",
  "transition": "release-lock-existing",
  "resume_to_exit_seconds": 4.786,
  "watcher_exit": 0,
  "diagnostic": "watcher: recovery state could not be persisted within 5s (marker lock held by pid 2838); stopping and retaining stale lock evidence",
  "ambient_values": {
    "FM_WATCHER_SHUTDOWN_LOCK_SECS": "300",
    "FM_RECOVERY_MARKER_LOCK_TIMEOUT": "300"
  },
  "marker_before": "announced:downtime:1636.1789474451.qAMl6i",
  "marker_after": "announced:downtime:1636.1789474451.qAMl6i",
  "holder_pid": 2838,
  "holder_survived": true,
  "stale_singleton_pid": "1665"
}
```

## Forced-stop diagnostic

The watcher used the host PATH; no fake timeout or backend tool was on its execution path.

```json
{
  "result": "pass",
  "injection": "SIGSTOP to real watcher from direct custom check; no production files modified",
  "ps_availability": "host ps",
  "assertion_exit": 1,
  "grandchild_pid": "75420",
  "recorded_reparented_child_pid": "75418",
  "reparented_child_ppid": "1"
}
```

```text
# fallback-timeout watcher still live 14s after TERM (150 polls); state below
# descendant tree (watcher pid 74563; recorded child pid 75418): pid ppid pgid stat wchan args
74563 74292 74288 T    -      bash /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/bin/fm-watch.sh
75418     1 75413 S    -      perl -e $SIG{TERM}="IGNORE"; my $g=fork; die $! unless defined $g; if (!$g) {sleep 60; exit} open my $gf, ">", $ENV{NM_GRANDCHILD} or die $!; print {$gf} "$g\n"; close $gf; open my $ready, ">", $ENV{FM_TEST_DESCENDANT_READY} or die $!; print {$ready} "ready\n"; close $ready; sleep 60
  75420 75418 75413 S    -      perl -e $SIG{TERM}="IGNORE"; my $g=fork; die $! unless defined $g; if (!$g) {sleep 60; exit} open my $gf, ">", $ENV{NM_GRANDCHILD} or die $!; print {$gf} "$g\n"; close $gf; open my $ready, ">", $ENV{FM_TEST_DESCENDANT_READY} or die $!; print {$ready} "ready\n"; close $ready; sleep 60
# fallback-timeout watcher stderr tail:
not ok - fallback-timeout watcher did not stop after the direct check returned
```

## Unavailable ps fails closed

The watcher used the host PATH; no fake timeout or backend tool was on its execution path.

```json
{
  "result": "pass",
  "injection": "SIGSTOP to real watcher from direct custom check; no production files modified",
  "ps_availability": "removed from command-scoped PATH",
  "assertion_exit": 1,
  "grandchild_pid": "79423",
  "recorded_reparented_child_pid": "79421",
  "reparented_child_ppid": "1"
}
```

```text
# is_live_non_zombie: ps reported no state for present pid 78954; UNKNOWN, not live
# is_live_non_zombie: ps reported no state for present pid 78954; UNKNOWN, not live
# fallback-timeout watcher still unreadable 14s after TERM (150 polls); state below
# descendant tree (watcher pid 78954; recorded child pid 79421): pid ppid pgid stat wchan args
78954 78854 74288 T    -      bash /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2JEJPE43XFXJCGYM3KFAX75/bin/fm-watch.sh
79421     1 79416 S    -      perl -e $SIG{TERM}="IGNORE"; my $g=fork; die $! unless defined $g; if (!$g) {sleep 60; exit} open my $gf, ">", $ENV{NM_GRANDCHILD} or die $!; print {$gf} "$g\n"; close $gf; open my $ready, ">", $ENV{FM_TEST_DESCENDANT_READY} or die $!; print {$ready} "ready\n"; close $ready; sleep 60
  79423 79421 79416 S    -      perl -e $SIG{TERM}="IGNORE"; my $g=fork; die $! unless defined $g; if (!$g) {sleep 60; exit} open my $gf, ">", $ENV{NM_GRANDCHILD} or die $!; print {$gf} "$g\n"; close $gf; open my $ready, ">", $ENV{FM_TEST_DESCENDANT_READY} or die $!; print {$ready} "ready\n"; close $ready; sleep 60
# fallback-timeout watcher stderr tail:
not ok - fallback-timeout watcher liveness was unreadable after the direct check returned
```

## Resource-fault RED to GREEN

```json
[
  {
    "mode": "mutant",
    "case": "test_lock_resource_failure_returns",
    "exit": 1,
    "seconds": 7.75,
    "output": "not ok - lock acquisition did not return on owner-directory creation failure"
  },
  {
    "mode": "mutant",
    "case": "test_shutdown_is_bounded_when_state_is_unwritable",
    "exit": 1,
    "seconds": 35.272,
    "output": "not ok - signaled watcher did not stop after owner-directory creation failed"
  },
  {
    "mode": "restored",
    "case": "test_lock_resource_failure_returns",
    "exit": 0,
    "seconds": 0.257,
    "output": "ok - lock acquisition returns nonzero when owner-directory creation fails"
  },
  {
    "mode": "restored",
    "case": "test_shutdown_is_bounded_when_state_is_unwritable",
    "exit": 0,
    "seconds": 16.381,
    "output": "ok - signaled watcher reaches its deadline on owner-directory creation failure (16s)"
  }
]
```

## Scope and limits

Targeted existing selectors: custom-check signal cleanup; returned descendants under both timeout fixture paths; held-marker shutdown; resource-fault acquisition and shutdown; live/gone/zombie/unreadable liveness.

The installed-timeout regression uses its existing timeout stand-in. Neither timeout nor gtimeout is installed on this host; the actual executable path is untested. Live custom-check validation used the real Perl fallback.

Resource mutations ran only against a disposable copy of bin/. Removing the resource distinction caused both expected hangs; restoring the target library passed both unchanged selectors. Existing polling budgets and ceilings were retained.

The alternate recovery-cleanup driver needed quoting and DEBUG-boundary corrections before its successful run. These were test setup issues; the final transcript records the successful live release-lock-existing case.

All nine runtime/test files are byte-identical to the pre-rebase merge. docs/watcher-continuity.md retains one upstream context change. Zero-context whole-branch patch IDs match; docs/configuration.md matches the new base. No new externally configurable timing remains.

The historical CI incident was not reproduced or assigned a new cause. This run establishes the current shutdown bounds, recovery behavior, and diagnostics.

No linter, formatter, static analyzer, full repository suite, remote CI, or pipeline-control command was run.
