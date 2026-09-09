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

ROOT="$PROCEVENT_CODE_ROOT"
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


now_ms() { perl -MTime::HiRes=time -e 'printf "%d\n", time * 1000'; }
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

