#!/usr/bin/env bash
# Behavior tests for the generic process-to-event runner and its Lavish adapter.
#
# The source under test is a fake blocking process that returns only when its
# trigger file appears, so completion is a real process event and no test here
# depends on a discovery timer. The Lavish adapter is exercised through its own
# public commands against the currently published poll shape; no live Lavish
# server is started.
#
# Delivery is deliberately NOT asserted as at-least-once or lossless: the
# published Lavish poll clears feedback destructively before returning it, so
# the only durability under test is the runner's own - output that reached the
# runner is stored before it is announced.
set -u

# shellcheck source=tests/lib.sh
. "/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2414ECRE7T77CAXN49RSA2F/tests/lib.sh"

ROOT="/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2414ECRE7T77CAXN49RSA2F"
TMP_ROOT=$(fm_test_tmproot fm-procevent-tests)
export FM_PROCEVENT_CLAIM_ROOT="$TMP_ROOT/claims"

BLOCKER="$TMP_ROOT/blocker.sh"
cat > "$BLOCKER" <<'SH'
#!/usr/bin/env bash
# Blocks until the trigger exists, then emits its payload. Completion is the
# event; nothing here polls on a schedule. The wait is bounded so a stub that
# escapes its test cannot keep spawning processes indefinitely.
trigger=$1; shift
while [ ! -e "$trigger" ]; do
  [ "$SECONDS" -lt "${FM_TEST_STUB_MAX_BLOCK_SECONDS:-120}" ] || exit 75
  sleep 0.05
done
[ -n "${BLOCKER_STDERR:-}" ] && printf 'noise on stderr\n' >&2
[ -n "${BLOCKER_EXIT:-}" ] && exit "$BLOCKER_EXIT"
printf '%s\n' "$@"
SH
chmod +x "$BLOCKER"

pe() { FM_HOME="$1" "$ROOT/bin/fm-procevent.sh" "${@:2}"; }

# Every home this suite registers a source in is tracked so teardown can stop
# its runners. A runner started by reconcile is detached and reparented, so a
# source that never completes outlives the suite unless its home is swept -
# removing the fixture directory does not stop an already-running child.
# tests/lib.sh owns that sweep and runs it from every cleanup path.
pe_register() {  # <home> <adapter> <source-id> -- <argv>...
  local home=$1 adapter=$2 id=$3
  shift 3
  fm_test_track_procevent_home "$home"
  pe "$home" register "$adapter" "$id" "$@"
}
new_home() { mkdir -p "$1/state"; }
wake_payloads() { awk -F '\t' '{print $5}' "$1/state/.wake-queue" 2>/dev/null; }

first_result() {  # <home> <source-id>: print the first captured result, if any
  local g
  for g in "$1/state/procevent-inbox/$2".*.result; do
    [ -e "$g" ] || continue
    printf '%s\n' "$g"
    return 0
  done
  return 1
}

count_results() {  # <home> <source-id>
  local g n=0
  for g in "$1/state/procevent-inbox/$2".*.result; do
    [ -e "$g" ] && n=$((n + 1))
  done
  printf '%s\n' "$n"
}

wait_for() {  # <file> [tries]
  local f=$1 n=${2:-100}
  for _ in $(seq 1 "$n"); do [ -s "$f" ] && return 0; sleep 0.1; done
  return 1
}

# <file> <count> [tries]: wait until <file> holds at least <count> lines. A
# detached runner appends its execution marker after the command that started it
# has already returned, so a caller that needs that append must wait for it
# rather than assume a fixed settle window covered it on a loaded machine.
wait_for_lines() {
  local f=$1 want=$2 n=${3:-100} have
  for _ in $(seq 1 "$n"); do
    have=$(wc -l < "$f" 2>/dev/null | tr -d ' ')
    case "$have" in ''|*[!0-9]*) have=0 ;; esac
    [ "$have" -ge "$want" ] && return 0
    sleep 0.1
  done
  return 1
}

hold_source_lock() {  # <source-id> <ready-file> <release-file>
  local id=$1 ready=$2 release=$3 parent=$$
  FM_HOME="$TMP_ROOT/lock-helper-home" bash -c '
    . "$1/bin/fm-pr-lib.sh"
    . "$1/bin/fm-wake-lib.sh"
    . "$1/bin/fm-procevent-lib.sh"
    fm_procevent_source_lock_acquire "$2" || exit 1
    trap "fm_procevent_source_lock_release \"$2\"" EXIT
    printf "ready\n" > "$3"
    while [ ! -e "$4" ]; do
      kill -0 "$5" 2>/dev/null || exit 0
      sleep 0.02
    done
  ' _ "$ROOT" "$id" "$ready" "$release" "$parent" &
  HOLDER_PID=$!
}

hold_source_lock_then_handle() {  # <home> <source-id> <sequence> <ready-file> <release-file>
  local home=$1 id=$2 seq=$3 ready=$4 release=$5 parent=$$
  FM_HOME="$home" bash -c '
    . "$1/bin/fm-pr-lib.sh"
    . "$1/bin/fm-wake-lib.sh"
    . "$1/bin/fm-procevent-lib.sh"
    fm_procevent_source_lock_acquire "$2" || exit 1
    trap "fm_procevent_source_lock_release \"$2\"" EXIT
    printf "ready\n" > "$4"
    while [ ! -e "$5" ]; do
      kill -0 "$6" 2>/dev/null || exit 1
      sleep 0.02
    done
    fm_procevent_mark_handled "$3/state" "$2" "$7"
  ' _ "$ROOT" "$id" "$home" "$ready" "$release" "$parent" "$seq" &
  HOLDER_PID=$!
}

# --- an accidentally orphaned runner is bounded by its owner ----------------
#
# Reproduces the shape that wedged a host: a listener detached into its own
# process group, reparented to init when its session ended, and left running for
# a day with its blocking child - and everything that child spawned - still
# executing. The cost was not the runner itself but the process churn under it,
# which is why this asserts the whole descendant tree stops, not just the leader.
#
# Scope is asserted alongside it, in the same run and against the same stub: a
# home whose session is still there keeps its runner. Reaping that keyed on the
# script or process name instead of the owning session would take both.

ORPHAN_STUB="$TMP_ROOT/orphan-stub.sh"
cat > "$ORPHAN_STUB" <<'SH'
#!/usr/bin/env bash
# A blocking source whose child keeps spawning processes, which is what a poll
# stub waiting on a trigger file actually does. The spawn rate is what turned a
# leftover listener into a host-wide storm, so the tick log is the evidence that
# the storm stopped and not merely that one pid went away.
marker=$1
( while [ "$SECONDS" -lt "${FM_TEST_STUB_MAX_BLOCK_SECONDS:-120}" ]; do
    printf 'tick\n' >> "$marker.ticks"
    sleep 0.1
  done ) &
printf '%s\n' "$!" > "$marker.descendant"
while [ ! -e "$marker.trigger" ]; do
  [ "$SECONDS" -lt "${FM_TEST_STUB_MAX_BLOCK_SECONDS:-120}" ] || exit 75
  sleep 0.1
done
printf 'orphan payload\n'
SH
chmod +x "$ORPHAN_STUB"

# The same shape without the spawn churn, for the home that exercises explicit
# retirement rather than the storm. Retirement refuses instead of signalling
# when it cannot confirm the runner's identity, that identity is read through
# `ps`, and the churning stub above starves that read often enough to make a
# single retirement attempt a race. The storm itself is already covered against
# the churning stub by the owner-loss reaping above, which asserts the tick log
# stops, so this home only needs a reparented listener holding a real
# descendant in its group.
QUIET_STUB="$TMP_ROOT/quiet-stub.sh"
cat > "$QUIET_STUB" <<'SH'
#!/usr/bin/env bash
marker=$1
( sleep "${FM_TEST_STUB_MAX_BLOCK_SECONDS:-120}" ) &
printf '%s\n' "$!" > "$marker.descendant"
while [ ! -e "$marker.trigger" ]; do
  [ "$SECONDS" -lt "${FM_TEST_STUB_MAX_BLOCK_SECONDS:-120}" ] || exit 75
  sleep 0.1
done
printf 'orphan payload\n'
SH
chmod +x "$QUIET_STUB"

# Short enough to observe, and driven through the same environment a real home
# uses, so the bound under test is the shipped one rather than a test-only path.
# One source of truth for the shortened lease and check these fixtures run under,
# so a case that derives a deadline from the guard's documented bound cannot
# silently diverge from the settings the guard is actually given.
PROOF_LEASE_SECONDS=2
PROOF_CHECK_SECONDS=1

# The documented bound, derived here rather than restated as a flat number.
#
# The whole-second lease comparison is part of the bound, not slack: a lease of
# N is honoured until its age reads N+1, so the lease term is N+1.
PROOF_LEASE_BOUND=$((PROOF_LEASE_SECONDS + 1))
# Detection is the lease plus ONE check interval. The guard still takes two
# consecutive failing reads before it acts - one unreadable read must not end a
# live runner - but they are spaced half an interval apart, so the pair fits
# inside the single interval this term budgets.
PROOF_DETECT_BOUND=$((PROOF_LEASE_BOUND + PROOF_CHECK_SECONDS))
# The stop's own ceiling: two seconds for the ordinary signal, then two for the
# forced one. Only a group that outlives the ordinary signal spends it, so a
# case whose stub exits on that signal uses PROOF_PROMPT_STOP instead.
PROOF_STOP_CEILING=4
PROOF_PROMPT_STOP=1
# Additive scheduling slack, never multiplicative. It absorbs a loaded host, not
# a slower guard: widening it past half a check interval would let a guard that
# spent a whole interval between its two reads hide inside it, which is the
# regression these deadlines exist to catch.
PROOF_LOAD_SLACK=2

orphan_pe() {  # <home> <command...>
  local home=$1
  shift
  FM_PROCEVENT_OWNER_LEASE_SECONDS="$PROOF_LEASE_SECONDS" \
    FM_PROCEVENT_OWNER_CHECK_SECONDS="$PROOF_CHECK_SECONDS" \
    FM_HOME="$home" "$ROOT/bin/fm-procevent.sh" "$@"
}

wait_gone() {  # <pid-or-group-spec> [tries]
  local spec=$1 n=${2:-160}
  for _ in $(seq 1 "$n"); do
    kill -0 "$spec" 2>/dev/null || return 0
    sleep 0.1
  done
  return 1
}

HORPHAN="$TMP_ROOT/orphan-dead-owner"; new_home "$HORPHAN"
fm_test_track_procevent_home "$HORPHAN"
HKEEP="$TMP_ROOT/orphan-live-owner"; new_home "$HKEEP"
fm_test_track_procevent_home "$HKEEP"
orphan_pe "$HORPHAN" register lavish orphan-src -- "$ORPHAN_STUB" "$TMP_ROOT/orphan-dead" >/dev/null
orphan_pe "$HKEEP" register lavish keep-src -- "$QUIET_STUB" "$TMP_ROOT/orphan-live" >/dev/null
orphan_pe "$HORPHAN" reconcile >/dev/null
orphan_pe "$HKEEP" reconcile >/dev/null

wait_for "$HORPHAN/state/procevent/orphan-src.runner" \
  || fail "the dead-owner listener never recorded its runner"
wait_for "$HKEEP/state/procevent/keep-src.runner" \
  || fail "the live-owner listener never recorded its runner"
wait_for "$TMP_ROOT/orphan-dead.descendant" \
  || fail "the dead-owner listener's child never spawned its own descendant"
ORPHAN_PID=$(cat "$HORPHAN/state/procevent/orphan-src.runner")
KEEP_PID=$(cat "$HKEEP/state/procevent/keep-src.runner")
ORPHAN_DESCENDANT=$(cat "$TMP_ROOT/orphan-dead.descendant")

# The reproduction condition itself: the listener is already an orphan in the
# kernel's sense before anything is asserted about reaping it.
orphan_ppid=$(ps -o ppid= -p "$ORPHAN_PID" 2>/dev/null | tr -d '[:space:]')
[ "$orphan_ppid" = 1 ] \
  || fail "the listener under test was not reparented away from its session (ppid $orphan_ppid)"
kill -0 -"$ORPHAN_PID" 2>/dev/null \
  || fail "the listener's process group was not running"
kill -0 "$ORPHAN_DESCENDANT" 2>/dev/null \
  || fail "the listener's descendant was not running"
pass "a detached listener starts reparented, with a live descendant tree under it"

# Only the second home's session stays present, on the same short bound, so the
# owning session is the single difference between the two listeners.
keep_owner_present() { orphan_pe "$HKEEP" reconcile >/dev/null 2>&1 || true; sleep 0.25; }

# This stub exits on the ordinary signal, so the stop ceiling is not spent here.
# The deadline is DERIVED from the documented bound; the timing case below is
# the one that pins the bound's worst case, while this one asserts that the
# reaping happens at all and cannot quietly take an unbounded amount of time.
orphan_bound=$((PROOF_DETECT_BOUND + PROOF_PROMPT_STOP))
deadline=$((SECONDS + orphan_bound + PROOF_LOAD_SLACK))
orphan_started=$SECONDS
while kill -0 -"$ORPHAN_PID" 2>/dev/null; do
  [ "$SECONDS" -lt "$deadline" ] \
    || fail "a listener whose owning session was gone kept its process group running for $((SECONDS - orphan_started))s, against a documented bound of ${orphan_bound}s"
  keep_owner_present
done
# The descendant goes down with the same group signal, so it needs no bound of
# its own beyond the slack that covers a loaded host.
deadline=$((SECONDS + PROOF_LOAD_SLACK))
while kill -0 "$ORPHAN_DESCENDANT" 2>/dev/null; do
  [ "$SECONDS" -lt "$deadline" ] \
    || fail "a listener whose owning session was gone left a descendant running"
  keep_owner_present
done
pass "a listener whose owning session is gone stops itself and its whole process group"

keep_owner_present
before=$(wc -l < "$TMP_ROOT/orphan-dead.ticks" | tr -d ' ')
deadline=$((SECONDS + 2))
while [ "$SECONDS" -lt "$deadline" ]; do keep_owner_present; done
after=$(wc -l < "$TMP_ROOT/orphan-dead.ticks" | tr -d ' ')
[ "$before" = "$after" ] \
  || fail "the reaped listener's descendant kept spawning processes ($before then $after)"
pass "reaping the listener stops the process churn under it"

keep_owner_present
kill -0 -"$KEEP_PID" 2>/dev/null \
  || fail "an identical listener in a home whose session is still there was reaped too"
pass "an identical listener in a home whose session is still there is untouched"

# Retirement remains the explicit path, and it must reach a listener that has
# already reparented, along with everything under it.
wait_for "$TMP_ROOT/orphan-live.descendant" \
  || fail "the live-owner listener's child never spawned its own descendant"
KEEP_DESCENDANT=$(cat "$TMP_ROOT/orphan-live.descendant")
keep_owner_present
orphan_pe "$HKEEP" retire keep-src >/dev/null
wait_gone "-$KEEP_PID" \
  || fail "retiring a source left its reparented listener's process group running"
wait_gone "$KEEP_DESCENDANT" \
  || fail "retiring a source left a descendant of its listener running"
pass "retiring a source reaps its reparented listener and every descendant under it"

# --- an expired runner's guard retries unproved cleanup ---------------------
#
# A stop the guard cannot PROVE must not end the guard. A descendant still
# finishing uninterruptible work outlives even the group KILL, and a guard that
# gave up after one attempt would walk away from a still-running expired runner.
#
# The unprovable attempt is injected through the signal the real path actually
# reads: `ps` answers ONE process-group query for the runner with a group it
# does not lead, which is exactly how a stop that cannot be proved is reported.
# Every other `ps` call, and every later one, is the real command.

RETRY_HOME="$TMP_ROOT/stop-retry"; new_home "$RETRY_HOME"
fm_test_track_procevent_home "$RETRY_HOME"
RETRY_STATE="$TMP_ROOT/stop-retry-state"; mkdir -p "$RETRY_STATE"
RETRY_BIN=$(fm_fakebin "$TMP_ROOT/stop-retry-bin")
REAL_PS=$(command -v ps) || fail "this host has no ps to build the retry fixture on"
cat > "$RETRY_BIN/ps" <<SH
#!/usr/bin/env bash
if [ "\$1" = -o ] && [ "\$2" = "pgid=" ] && [ "\$3" = -p ] \\
  && [ -s "\$STOP_RETRY_STATE/target" ] \\
  && [ "\$4" = "\$(cat "\$STOP_RETRY_STATE/target")" ] \\
  && [ ! -e "\$STOP_RETRY_STATE/spent" ]; then
  : > "\$STOP_RETRY_STATE/spent"
  printf ' 999999\n'
  exit 0
fi
exec "$REAL_PS" "\$@"
SH
chmod +x "$RETRY_BIN/ps"

retry_pe() {  # <command...>
  PATH="$RETRY_BIN:$PATH" STOP_RETRY_STATE="$RETRY_STATE" \
    FM_PROCEVENT_OWNER_LEASE_SECONDS=2 FM_PROCEVENT_OWNER_CHECK_SECONDS=1 \
    FM_HOME="$RETRY_HOME" "$ROOT/bin/fm-procevent.sh" "$@"
}

retry_pe register lavish retry-src -- "$ORPHAN_STUB" "$TMP_ROOT/stop-retry-marker" >/dev/null
retry_pe reconcile >/dev/null
wait_for "$RETRY_HOME/state/procevent/retry-src.runner" \
  || fail "the retry listener never recorded its runner"
RETRY_PID=$(cat "$RETRY_HOME/state/procevent/retry-src.runner")
# Armed only now: the runner already proved its own process group at startup,
# and arming earlier would fail that assertion instead of the stop under test.
printf '%s\n' "$RETRY_PID" > "$RETRY_STATE/target"
wait_for "$TMP_ROOT/stop-retry-marker.descendant" \
  || fail "the retry listener's child never spawned its own descendant"
RETRY_DESCENDANT=$(cat "$TMP_ROOT/stop-retry-marker.descendant")

deadline=$((SECONDS + 60))
while kill -0 -"$RETRY_PID" 2>/dev/null; do
  [ "$SECONDS" -lt "$deadline" ] \
    || fail "the guard gave up on an expired runner after a stop it could not prove"
  sleep 0.5
done
[ -e "$RETRY_STATE/spent" ] \
  || fail "the unprovable stop attempt this test injects never happened"
wait_gone "$RETRY_DESCENDANT" \
  || fail "the guard stopped retrying before the expired runner's descendant was reaped"
pass "a stop the guard cannot prove is retried until the expired runner is reaped"

# --- a stop reaches a child that does not die on the ordinary signal ---------
#
# Every reaper here sends the ordinary stop signal to the runner's process group
# and escalates only if the group outlives it. Both halves of that escalation
# were broken, in ways that hid each other:
#
#   - The stop held the per-source lock across its wait while the runner's own
#     exit cleanup waited for that same lock, so the runner outlived the ordinary
#     signal every time and the forced kill silently became the normal path.
#   - The escalation re-derived ownership from the leader, so once the leader did
#     die to the stop's own signal it read that success as a leaderless group and
#     refused to escalate at all.
#
# With only the first repaired, the second turned every stop of a signal-proof
# child into a refusal that left it running. They are asserted together because
# they only hold together.
#
# Earlier fixtures include TERM-resistant children and deliberately kept-alive
# leaders. The cases below also exercise escalation after TERM ends the leader.

# Millisecond clock for supplementary retirement and stop-window measurements;
# the healthy-stop verdict below requires attached-start status 143 (TERM).
now_ms() { perl -MTime::HiRes=time -e 'printf "%d\n", time * 1000'; }

SIGNAL_PROOF_STUB="$TMP_ROOT/signal-proof-stub.sh"
cat > "$SIGNAL_PROOF_STUB" <<'SH'
#!/usr/bin/env bash
# A blocking source whose child handles the ordinary stop signal and keeps
# waiting - the shape a poll client with its own shutdown handler presents while
# a request is still outstanding. Reaching it requires a real escalation. The
# signal log is what proves the child was signalled and survived, rather than
# never having been signalled at all. The wait stays bounded so an escaped stub
# cannot outlive the suite.
marker=$1
trap 'printf "signalled\n" >> "$marker.signals"' TERM INT HUP
printf '%s\n' "$$" > "$marker.child"
while [ ! -e "$marker.trigger" ]; do
  [ "$SECONDS" -lt "${FM_TEST_STUB_MAX_BLOCK_SECONDS:-120}" ] || exit 75
  sleep 0.1 &
  wait $!
done
printf 'signal-proof payload\n'
SH
chmod +x "$SIGNAL_PROOF_STUB"

trap '[ -z "${PROOF_RELEASE:-}" ] || touch "$PROOF_RELEASE"; fm_test_cleanup' EXIT
for proof_state in absent zombie; do
  HPROOF="$TMP_ROOT/signal-proof-retire-$proof_state"; new_home "$HPROOF"
  PROOF_MARKER="$HPROOF/poll"
  pe_register "$HPROOF" lavish proof-src -- "$SIGNAL_PROOF_STUB" "$PROOF_MARKER" >/dev/null
  PROOF_RELEASE=
  if [ "$proof_state" = zombie ]; then
    PROOF_RELEASE="$HPROOF/reap"
    FM_HOME="$HPROOF" FM_PROC_ROOT_OVERRIDE="$TMP_ROOT/no-proof-proc" \
      perl - "$PROOF_RELEASE" "$ROOT/bin/fm-procevent.sh" _start proof-src >"$HPROOF/start.log" 2>&1 <<'PL' &
my $release = shift @ARGV;
defined(my $pid = fork) or exit 125;
if ($pid == 0) {
  setpgrp(0, 0) or exit 125;
  $ENV{FM_PROCEVENT_RUNNER_GROUP} = $$;
  exec @ARGV;
  exit 125;
}
my $deadline = time + ($ENV{FM_TEST_STUB_MAX_BLOCK_SECONDS} // 120);
while (!-e $release && time < $deadline) { select undef, undef, undef, 0.05; }
waitpid($pid, 0) == $pid or exit 125;
PL
  else
    FM_PROC_ROOT_OVERRIDE="$TMP_ROOT/no-proof-proc" \
      pe "$HPROOF" start proof-src >"$HPROOF/start.log" 2>&1 &
  fi
  PROOF_START=$!
  wait_for "$HPROOF/state/procevent/proof-src.runner" \
    || fail "the signal-proof listener never recorded its runner"
  PROOF_PID=$(cat "$HPROOF/state/procevent/proof-src.runner")
  wait_for "$PROOF_MARKER.child" || fail "the signal-proof child never started"
  PROOF_CHILD=$(cat "$PROOF_MARKER.child")
  FM_PROC_ROOT_OVERRIDE="$TMP_ROOT/no-proof-proc" \
    pe "$HPROOF" retire proof-src >"$HPROOF/retire.log" 2>&1 &
  PROOF_STOP=$!
  proof_transition=0
  for _ in $(seq 1 100); do
    if [ "$proof_state" = zombie ]; then
      case "$(ps -o stat= -p "$PROOF_PID" 2>/dev/null | tr -d '[:space:]')" in
        Z*) proof_transition=1; break ;;
      esac
    elif ! kill -0 "$PROOF_PID" 2>/dev/null; then
      proof_transition=1
      break
    fi
    sleep 0.05
  done
  proof_survivor=0
  kill -0 "$PROOF_CHILD" 2>/dev/null && proof_survivor=1
  proof_reaped=0
  for _ in $(seq 1 100); do
    if ! kill -0 "$PROOF_CHILD" 2>/dev/null; then proof_reaped=1; break; fi
    sleep 0.1
  done
  [ -z "$PROOF_RELEASE" ] || touch "$PROOF_RELEASE"
  PROOF_RELEASE=
  proof_status=0
  wait "$PROOF_STOP" || proof_status=$?
  [ "$proof_reaped" -eq 1 ] || kill -KILL -"$PROOF_PID" 2>/dev/null || true
  wait "$PROOF_START" 2>/dev/null || true
  [ "$proof_transition" -eq 1 ] || fail "the runner never became $proof_state after TERM"
  [ "$proof_survivor" -eq 1 ] || fail "no child survived the $proof_state leader's TERM"
  [ "$proof_reaped" -eq 1 ] || fail "escalation abandoned a child behind a $proof_state leader"
  [ "$proof_status" -eq 0 ] || fail "retiring the $proof_state leader's group reported failure"
  wait_gone "-$PROOF_PID" || fail "retirement left the $proof_state leader's group running"
  [ -s "$PROOF_MARKER.signals" ] || fail "the signal-proof child never received TERM"
  pass "retirement escalates after TERM leaves a surviving child ($proof_state leader)"
done
trap fm_test_cleanup EXIT

# --- the owner guard reaps a signal-proof child too --------------------------
#
# The guard is where the time bound on a leaked listener lives, so it is the half
# that matters most: a guard that signals, loses its leader to its own signal and
# then walks away leaves the survivor unreachable by anything at all - worse than
# no guard, because the leader it destroyed was the only proof of ownership left.

HPGUARD="$TMP_ROOT/signal-proof-guard"; new_home "$HPGUARD"
fm_test_track_procevent_home "$HPGUARD"
orphan_pe "$HPGUARD" register lavish proof-guard-src \
  -- "$SIGNAL_PROOF_STUB" "$TMP_ROOT/proof-guard" >/dev/null
orphan_pe "$HPGUARD" reconcile >/dev/null
# The owner is kept present until the fixture is fully up, because the input
# under test is an owner that GOES AWAY, not a runner that never finished
# starting: on a loaded host the short lease here can otherwise expire while the
# runner is still between fork and its first recorded state.
deadline=$((SECONDS + 60))
until [ -s "$HPGUARD/state/procevent/proof-guard-src.runner" ] \
  && [ -s "$TMP_ROOT/proof-guard.child" ]; do
  [ "$SECONDS" -lt "$deadline" ] || fail "the guarded signal-proof listener never started"
  orphan_pe "$HPGUARD" reconcile >/dev/null 2>&1 || true
  sleep 0.25
done
GUARD_PID=$(cat "$HPGUARD/state/procevent/proof-guard-src.runner")
GUARD_CHILD=$(cat "$TMP_ROOT/proof-guard.child")

# Nothing refreshes this home's lease from here on, which is the whole input.
#
# The deadline is DERIVED from the bound this case exists to defend, not a flat
# wall-clock number. The documented bound is the lease term, plus ONE check
# interval for detection - the guard's two confirming reads are half an interval
# apart and both fit inside it - plus the stop's own grace, its ordinary signal
# window and then its forced one. THIS case does spend that grace, because its
# child ignores the ordinary signal; that is what separates its allowance from
# the ordinary-stop case above.
#
# A flat 60 seconds here would pass a guard that took 55, so it could not go red
# for the reason it names. The slack is additive and stays under half a check
# interval for the same reason: it must never be widened to make a slow guard
# pass, because that converts this assertion back into the decoration it was.
guard_bound=$((PROOF_DETECT_BOUND + PROOF_STOP_CEILING))
deadline=$((SECONDS + guard_bound + PROOF_LOAD_SLACK))
guard_started=$SECONDS
while kill -0 -"$GUARD_PID" 2>/dev/null; do
  [ "$SECONDS" -lt "$deadline" ] \
    || fail "the guard exceeded its bound: still holding the group after $((SECONDS - guard_started))s, against a documented bound of ${guard_bound}s"
  sleep 0.5
done
wait_gone "$GUARD_CHILD" \
  || fail "the guard stopped at the leader and left the signal-proof child running"
[ -s "$TMP_ROOT/proof-guard.signals" ] \
  || fail "the guarded child was never signalled, so nothing about escalation was exercised"
pass "an expired runner's guard escalates past a signal-proof child"

# --- the guard's bound is one check interval, not two ------------------------
#
# The case above proves the guard reaps at all. This one measures HOW LONG it
# may take, because that is the number the operating contract states and the one
# a later change can quietly double.
#
# The bound: the lease term, plus ONE check interval. The guard still refuses to
# act on a single failed read - the case after this one is what defends that -
# but its two confirming reads are spaced half an interval apart, so the pair
# fits inside the one interval budgeted here. A guard that put a whole interval
# between them would spend two, and this deadline is sized to catch exactly that.
#
# THE PHASE IS OBSERVED AND ENFORCED, NOT ASSUMED. Where the lease expiry falls
# relative to the guard's own check clock decides whether a run lands near the
# bound or well inside it, and a sampled phase would let a guard spending two
# intervals slip under this deadline on a lucky alignment. So the lease is
# synchronized to the guard's own FIRST observed lease read, every later real
# read is recorded, and the case then REFUSES unless one of those reads proves
# the required phase: fresh, before expiry, and late enough that two further
# full intervals could not finish before the deadline.
#
# Pinning the phase by construction instead - from an assumed startup time - is
# what an earlier version of this case did, and it is not enough: the day
# startup reaches two seconds it silently stops rejecting a two-interval guard
# and goes on passing. A bound that cannot fail for the reason it names is the
# defect this whole delivery exists to correct, so an unestablished precondition
# refuses here rather than proceeding on trust.
BOUND_LEASE_SECONDS=7
BOUND_CHECK_SECONDS=6
# The whole-second lease comparison is part of the bound, not slack: a lease of
# N is honoured until its age reads N+1.
bound_lease_term=$((BOUND_LEASE_SECONDS + 1))
bound_detect=$((bound_lease_term + BOUND_CHECK_SECONDS))
# This stub exits on the ordinary signal, so the stop's escalation ceiling is
# not spent here; one second covers signalling and exit against a measured
# ~0.4s for a whole retire command on this host.
bound_total=$((bound_detect + PROOF_PROMPT_STOP))
# Additive load slack, under half a check interval for the reason above. The
# invariant is asserted rather than left to a comment, because a later widening
# is exactly what would disarm the deadline below.
bound_deadline_s=$((bound_total + PROOF_LOAD_SLACK))
[ "$((PROOF_LOAD_SLACK * 2))" -lt "$BOUND_CHECK_SECONDS" ] \
  || fail "the bound fixture's load slack must stay below half a check interval"

now_mono() {
  perl -MTime::HiRes=clock_gettime,CLOCK_MONOTONIC -e \
    'printf "%.3f\n", clock_gettime(CLOCK_MONOTONIC)'
}
mono_since() {  # <monotonic-reference>: seconds elapsed, one decimal
  perl -e 'printf "%.1f\n", $ARGV[0] - $ARGV[1]' "$(now_mono)" "$1"
}

HBOUND="$TMP_ROOT/guard-bound"; new_home "$HBOUND"
fm_test_track_procevent_home "$HBOUND"
BOUND_STATE="$TMP_ROOT/guard-bound-state"; mkdir -p "$BOUND_STATE"
BOUND_BIN=$(fm_fakebin "$TMP_ROOT/guard-bound-bin")
REAL_PERL=$(command -v perl) || fail "this host has no perl to observe the guard's lease reads"
# Observes the real lease-age reads, identified by the lease-age program's own
# text, and changes nothing about what they return. The FIRST such read becomes
# the lease reference - that is the synchronization - and every later one is
# recorded with the value it read and the interval it spanned, which is the
# evidence the phase assertion below consumes.
cat > "$BOUND_BIN/perl" <<SH
#!/usr/bin/env bash
for arg in "\$@"; do
  case \$arg in
    *'int(\$now - \$value)'*)
      started=\$("$REAL_PERL" -MTime::HiRes=clock_gettime,CLOCK_MONOTONIC -e \\
        'printf "%.6f\\n", clock_gettime(CLOCK_MONOTONIC)') || exit 1
      age=\$("$REAL_PERL" "\$@") || exit \$?
      finished=\$("$REAL_PERL" -MTime::HiRes=clock_gettime,CLOCK_MONOTONIC -e \\
        'printf "%.6f\\n", clock_gettime(CLOCK_MONOTONIC)') || exit 1
      if [ ! -s "\$GUARD_BOUND_STATE/reference" ]; then
        printf '%s\\n' "\$finished" > "\$FM_HOME/state/procevent/.owner-lease" || exit 1
        printf '%s\\n' "\$finished" > "\$GUARD_BOUND_STATE/reference" || exit 1
      else
        printf '%s\\t%s\\t%s\\t%s\\n' "\$started" "\$finished" "\$age" "\${!#}" \\
          >> "\$GUARD_BOUND_STATE/reads" || exit 1
      fi
      printf '%s\\n' "\$age"
      exit 0
      ;;
  esac
done
exec "$REAL_PERL" "\$@"
SH
chmod +x "$BOUND_BIN/perl"
bound_pe() {
  PATH="$BOUND_BIN:$PATH" GUARD_BOUND_STATE="$BOUND_STATE" \
    FM_PROCEVENT_OWNER_LEASE_SECONDS="$BOUND_LEASE_SECONDS" \
    FM_PROCEVENT_OWNER_CHECK_SECONDS="$BOUND_CHECK_SECONDS" \
    FM_HOME="$HBOUND" "$ROOT/bin/fm-procevent.sh" "$@"
}
bound_pe register lavish bound-src -- "$QUIET_STUB" "$TMP_ROOT/guard-bound-marker" >/dev/null
bound_pe reconcile >/dev/null
wait_for "$HBOUND/state/procevent/bound-src.runner" \
  || fail "the bound fixture's listener never recorded its runner"
wait_for "$TMP_ROOT/guard-bound-marker.descendant" \
  || fail "the bound fixture's listener never spawned its descendant"
BOUND_PID=$(cat "$HBOUND/state/procevent/bound-src.runner")
BOUND_DESCENDANT=$(cat "$TMP_ROOT/guard-bound-marker.descendant")
# Elapsed is measured from the refresh the guard itself reads, not from a
# wall-clock moment near it, so the fixture's own startup cost cannot be
# mistaken for guard latency in either direction.
bound_reference=$(cat "$HBOUND/state/procevent/.owner-lease") \
  || fail "the bound fixture recorded no owner lease to measure against"
[ "$bound_reference" = "$(cat "$BOUND_STATE/reference" 2>/dev/null)" ] \
  || fail "the bound fixture did not synchronize its lease to an observed guard read"
while kill -0 -"$BOUND_PID" 2>/dev/null; do
  [ "$(mono_since "$bound_reference" | cut -d. -f1)" -lt "$bound_deadline_s" ] \
    || fail "the guard exceeded its bound: group still running $(mono_since "$bound_reference")s after the last owner activity, against a documented bound of ${bound_total}s (lease term ${bound_lease_term}s + one ${BOUND_CHECK_SECONDS}s check interval + ${PROOF_PROMPT_STOP}s stop)"
  sleep 0.2
done
bound_elapsed=$(mono_since "$bound_reference")
# The loop above only ever checks the clock while the group is still alive, so a
# sampler descheduled past the deadline would see the group already gone and
# report success. Check the OBSERVED completion time too: a late observation
# must not certify timely completion.
[ "${bound_elapsed%%.*}" -lt "$bound_deadline_s" ] \
  || fail "the guard's completion was first observed ${bound_elapsed}s after the last owner activity, beyond its ${bound_deadline_s}s deadline"
# FAIL CLOSED ON THE PHASE. One recorded read must prove the run was in the part
# of the interval this deadline can actually judge: it read the synchronized
# reference, it was still fresh (pre-expiry), and it began late enough that two
# further FULL intervals could not finish before the deadline. Without such a
# read the case refuses - it does not pass on trust, however quickly the group
# happened to stop.
perl - "$BOUND_STATE/reads" "$bound_reference" "$BOUND_LEASE_SECONDS" \
  "$BOUND_CHECK_SECONDS" "$bound_deadline_s" <<'PL' \
  || fail "the bound fixture could not establish the required pre-expiry guard-read phase"
use strict;
use warnings;
my ($path, $reference, $lease, $check, $deadline) = @ARGV;
open my $reads, '<', $path or exit 1;
while (<$reads>) {
  chomp;
  my ($started, $finished, $age, $value) = split /\t/;
  next unless defined $value && $value eq $reference && $age <= $lease;
  next unless $started >= $reference && $finished >= $started;
  next unless $finished < $reference + $lease + 1;
  next unless $started + 2 * $check >= $reference + $deadline;
  printf "guard phase: fresh read %.3f-%.3fs, expiry %ss, two full intervals could not finish before %.3fs (deadline %ss)\n",
    $started - $reference, $finished - $reference, $lease + 1,
    $started - $reference + 2 * $check, $deadline;
  exit 0;
}
exit 1;
PL
wait_gone "$BOUND_DESCENDANT" \
  || fail "the guard stopped at the leader and left its descendant running"
printf 'guard bound: lease=%ss check=%ss reaped %ss after the last owner activity, documented bound %ss\n' \
  "$BOUND_LEASE_SECONDS" "$BOUND_CHECK_SECONDS" "$bound_elapsed" "$bound_total"
pass "an orphaned runner is reaped within the lease plus ONE check interval"

# --- a zero-prefixed interval still starts a listener, and halves correctly ---
#
# OUR OWN REGRESSION, found in review before this change was published. The
# interval validator accepts a zero-prefixed value and `[` compares it as
# decimal, but the half-interval arithmetic introduced above reads `$(( ))`,
# which is octal for a leading zero: 010 halved to 4 instead of 5, and 08 was
# not a number at all, so the guard died before reporting ready and the runner
# failed closed and never listened.
#
# Asserted through the executable interface rather than by reading the source:
# a real listener is started at each value, and the guard's actual sleep
# argument is observed. Reading `10#` out of the script would prove nothing.
INTERVAL_BIN=$(fm_fakebin "$TMP_ROOT/decimal-interval-bin")
REAL_SLEEP=$(command -v sleep) || fail "this host has no sleep to observe guard intervals"
cat > "$INTERVAL_BIN/sleep" <<SH
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "\$INTERVAL_SLEEP_LOG"
exec "$REAL_SLEEP" "\$@"
SH
chmod +x "$INTERVAL_BIN/sleep"
for interval in 08 010; do
  case "$interval" in
    08) expected_half=4 ;;
    010) expected_half=5 ;;
  esac
  HINTERVAL="$TMP_ROOT/decimal-interval-$interval"; new_home "$HINTERVAL"
  pe_register "$HINTERVAL" lavish "interval-$interval" \
    -- "$QUIET_STUB" "$HINTERVAL/poll" >/dev/null
  PATH="$INTERVAL_BIN:$PATH" INTERVAL_SLEEP_LOG="$HINTERVAL/sleeps" \
    FM_PROCEVENT_OWNER_CHECK_SECONDS="$interval" \
    pe "$HINTERVAL" reconcile >/dev/null
  wait_for "$HINTERVAL/poll.descendant" \
    || fail "a zero-prefixed decimal interval ($interval) prevented the listener from starting"
  for _ in $(seq 1 100); do
    grep -qx "$expected_half" "$HINTERVAL/sleeps" 2>/dev/null && break
    sleep 0.1
  done
  grep -qx "$expected_half" "$HINTERVAL/sleeps" \
    || fail "the guard did not sleep half of the decimal interval $interval (expected ${expected_half}s)"
  pe "$HINTERVAL" retire "interval-$interval" >/dev/null \
    || fail "retiring the decimal-interval listener ($interval) reported failure"
  printf 'decimal interval: %s halves to %ss and its listener started\n' "$interval" "$expected_half"
done
pass "a zero-prefixed decimal interval starts its listener and halves as decimal"

# --- one unreadable read still does not end a live runner --------------------
#
# The bound above was tightened by moving the guard's two reads closer together,
# NOT by dropping the second one. This is what that second read is for, asserted
# separately so the two cannot be traded for each other by accident: against a
# home that is still alive, one failed read must reset the count, not stop the
# runner.
#
# The failure is injected where the real path actually reads. ONE lease read
# fails, exactly once, identified by the lease-age program's own text so no
# other call in the runner is touched; every read before and after it is the
# real command, and the home's lease stays long and fresh throughout. The single
# failed read is therefore the only thing wrong that the guard can see.

DEBOUNCE_HOME="$TMP_ROOT/lease-debounce"; new_home "$DEBOUNCE_HOME"
fm_test_track_procevent_home "$DEBOUNCE_HOME"
DEBOUNCE_STATE="$TMP_ROOT/lease-debounce-state"; mkdir -p "$DEBOUNCE_STATE"
DEBOUNCE_BIN=$(fm_fakebin "$TMP_ROOT/lease-debounce-bin")
REAL_PERL=$(command -v perl) || fail "this host has no perl to build the debounce fixture on"
cat > "$DEBOUNCE_BIN/perl" <<SH
#!/usr/bin/env bash
if [ -s "\$LEASE_DEBOUNCE_STATE/armed" ] && [ ! -s "\$LEASE_DEBOUNCE_STATE/spent" ]; then
  for arg in "\$@"; do
    case \$arg in
      *'int(\$now - \$value)'*)
        printf 'spent\n' > "\$LEASE_DEBOUNCE_STATE/spent"
        exit 1
        ;;
    esac
  done
fi
exec "$REAL_PERL" "\$@"
SH
chmod +x "$DEBOUNCE_BIN/perl"

# A long lease and a short check: many reads happen inside the observation
# window, and none of them can go stale on their own during it.
DEBOUNCE_LEASE_SECONDS=30
DEBOUNCE_CHECK_SECONDS=1
debounce_pe() {
  PATH="$DEBOUNCE_BIN:$PATH" LEASE_DEBOUNCE_STATE="$DEBOUNCE_STATE" \
    FM_PROCEVENT_OWNER_LEASE_SECONDS="$DEBOUNCE_LEASE_SECONDS" \
    FM_PROCEVENT_OWNER_CHECK_SECONDS="$DEBOUNCE_CHECK_SECONDS" \
    FM_HOME="$DEBOUNCE_HOME" "$ROOT/bin/fm-procevent.sh" "$@"
}
debounce_pe register lavish debounce-src -- "$QUIET_STUB" "$TMP_ROOT/lease-debounce-marker" >/dev/null
debounce_pe reconcile >/dev/null
wait_for "$DEBOUNCE_HOME/state/procevent/debounce-src.runner" \
  || fail "the debounce fixture's listener never recorded its runner"
DEBOUNCE_PID=$(cat "$DEBOUNCE_HOME/state/procevent/debounce-src.runner")
# Armed only now. The guard proves the lease once before it reports ready, and
# failing THAT read would refuse the runner outright instead of exercising the
# debounce this case is about.
printf 'armed\n' > "$DEBOUNCE_STATE/armed"
wait_for "$DEBOUNCE_STATE/spent" \
  || fail "the single failed lease read this case injects never happened"
# Several further checks at the configured interval. A guard that acted on one
# failed read would have stopped the group during them.
sleep $((DEBOUNCE_CHECK_SECONDS * 4))
kill -0 -"$DEBOUNCE_PID" 2>/dev/null \
  || fail "one unreadable lease read ended a runner whose home was still alive"
debounce_pe retire debounce-src >/dev/null \
  || fail "retiring the debounce fixture's source reported failure"
wait_gone "-$DEBOUNCE_PID" \
  || fail "retiring the debounce fixture left its process group running"
pass "one unreadable read does not end a live runner"

# --- the ordinary stop signal is what stops a runner ------------------------
#
# The forced kill is the backstop, not the normal path. When it carries every
# stop, it stops being able to report that anything went wrong - which is exactly
# how a listener that could not be stopped looked identical to one that could.

HPROMPT="$TMP_ROOT/prompt-stop"; new_home "$HPROMPT"
pe_register "$HPROMPT" lavish prompt-src -- "$QUIET_STUB" "$TMP_ROOT/prompt-stop" >/dev/null
pe "$HPROMPT" start prompt-src >"$TMP_ROOT/prompt-start.log" 2>&1 &
PROMPT_START_PID=$!
wait_for "$HPROMPT/state/procevent/prompt-src.runner" \
  || fail "the promptly-stopping listener never recorded its runner"
PROMPT_PID=$(cat "$HPROMPT/state/procevent/prompt-src.runner")
wait_for "$TMP_ROOT/prompt-stop.descendant" \
  || fail "the promptly-stopping listener's child never spawned its own descendant"
stop_window_ms() {
  local from to
  from=$(now_ms)
  for _ in $(seq 1 20); do sleep 0.1; done
  to=$(now_ms)
  printf '%s\n' "$((to - from))"
}
window_before=$(stop_window_ms)
start=$(now_ms)
pe "$HPROMPT" retire prompt-src >/dev/null || fail "retiring a healthy listener reported failure"
elapsed=$(( $(now_ms) - start ))
window_after=$(stop_window_ms)
prompt_status=0
wait "$PROMPT_START_PID" || prompt_status=$?
wait_gone "-$PROMPT_PID" || fail "retiring a healthy listener left its process group running"
[ "$prompt_status" -eq 143 ] \
  || fail "the runner did not exit on TERM (start status=$prompt_status, retirement=${elapsed}ms, sampled windows=${window_before}/${window_after}ms)"
printf 'ordinary stop: start status=%s retirement=%sms sampled windows=%s/%sms\n' \
  "$prompt_status" "$elapsed" "$window_before" "$window_after"
pass "a runner exits on the ordinary stop signal instead of outliving it"

# --- a crashed leader's group is still refused -------------------------------
#
# The escalation above accepts a leaderless group in exactly one place: inside
# the stop that just proved and signalled that generation itself. Whether a group
# whose leader died to something ELSE may ever be signalled is a separate open
# question, and this pins that it stays refused - so the escalation cannot widen
# into an answer to it by accident.

HCRASH="$TMP_ROOT/crashed-leader"; new_home "$HCRASH"
pe_register "$HCRASH" lavish crash-src -- "$QUIET_STUB" "$TMP_ROOT/crash-leader" >/dev/null
pe "$HCRASH" reconcile >/dev/null
wait_for "$HCRASH/state/procevent/crash-src.runner" \
  || fail "the crash-fixture listener never recorded its runner"
CRASH_PID=$(cat "$HCRASH/state/procevent/crash-src.runner")
wait_for "$TMP_ROOT/crash-leader.descendant" \
  || fail "the crash-fixture listener's child never spawned its own descendant"
kill -KILL "$CRASH_PID" 2>/dev/null || fail "the crash fixture could not stop its own leader"
deadline=$((SECONDS + 10))
while kill -0 "$CRASH_PID" 2>/dev/null; do
  [ "$SECONDS" -lt "$deadline" ] || fail "the crash fixture's leader never died"
  sleep 0.1
done
kill -0 -"$CRASH_PID" 2>/dev/null \
  || fail "the crash fixture left no surviving group, so nothing was refused"

out=$(pe "$HCRASH" retire crash-src 2>&1) && fail "retirement claimed success on a crashed leader's group"
assert_contains "$out" "cannot confirm runner identity" \
  "a crashed leader's group is refused with its own diagnostic"
assert_present "$HCRASH/state/procevent/crash-src.source" \
  "a refused retirement leaves the source registered"
kill -0 -"$CRASH_PID" 2>/dev/null \
  || fail "a refused retirement signalled the leaderless group anyway"
pass "a group whose leader died to something else is still refused, not signalled"
kill -KILL -"$CRASH_PID" 2>/dev/null || true

printf '\ntargeted procevent lifetime cases passed\n'
