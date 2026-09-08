#!/usr/bin/env bash
export TMPDIR=/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M20TSCZM0KDMYBZKD1S7KSYQ/.local-test-procevent/tmp
unset FM_STATE_OVERRIDE FM_ROOT_OVERRIDE FM_PROCEVENT_IN_RUNNER FM_PROCEVENT_RUNNER_GROUP
set -u

# shellcheck source=tests/lib.sh
. /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M20TSCZM0KDMYBZKD1S7KSYQ/tests/lib.sh

ROOT=/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M20TSCZM0KDMYBZKD1S7KSYQ
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
orphan_pe() {  # <home> <command...>
  local home=$1
  shift
  FM_PROCEVENT_OWNER_LEASE_SECONDS=2 FM_PROCEVENT_OWNER_CHECK_SECONDS=1 \
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

for post_term_case in mismatch unreadable unreadable-pgid nonleader; do
  HPOST_TERM="$TMP_ROOT/post-term-$post_term_case"; new_home "$HPOST_TERM"
  POST_TERM_SOURCE="$HPOST_TERM/source.sh"
  POST_TERM_PID="$HPOST_TERM/child.pid"
  POST_TERM_SIGNALS="$HPOST_TERM/child.signals"
  cat > "$POST_TERM_SOURCE" <<'SH'
#!/usr/bin/env bash
trap 'printf "signalled\n" >> "$2"' TERM
printf '%s\n' "$$" > "$1"
while [ "$SECONDS" -lt "${FM_TEST_STUB_MAX_BLOCK_SECONDS:-120}" ]; do sleep 1; done
SH
  chmod +x "$POST_TERM_SOURCE"
  POST_TERM_BIN=$(fm_fakebin "$HPOST_TERM/tools")
  REAL_PS=$(command -v ps) || fail "the post-TERM reuse fixture requires ps"
  pe_register "$HPOST_TERM" lavish post-term-src -- \
    "$POST_TERM_SOURCE" "$POST_TERM_PID" "$POST_TERM_SIGNALS" >/dev/null
  FM_PROC_ROOT_OVERRIDE="$TMP_ROOT/no-post-term-proc" \
    FM_PROCEVENT_OWNER_CHECK_SECONDS=5 pe "$HPOST_TERM" reconcile >/dev/null
  wait_for "$POST_TERM_PID" || fail "the post-TERM reuse fixture did not start"
  wait_for "$FM_PROCEVENT_CLAIM_ROOT/post-term-src.claim" \
    || fail "the post-TERM reuse fixture did not claim its source"
  POST_TERM_RUNNER=$(sed -n '2p' "$FM_PROCEVENT_CLAIM_ROOT/post-term-src.claim")
  kill -STOP "$POST_TERM_RUNNER" || fail "the post-TERM fixture could not keep its leader alive"
  cat > "$POST_TERM_BIN/ps" <<SH
#!/usr/bin/env bash
if [ "\${1-}" = -p ] && [ "\${2-}" = "$POST_TERM_RUNNER" ] \
  && [ "\${3-}" = -o ] && [ "\${4-}" = lstart= ]; then
  if [ "$post_term_case" = mismatch ]; then
    printf 'reused identity\n'
    exit 0
  fi
  [ ! -s "$POST_TERM_SIGNALS" ] || exit 1
fi
if [ "\${1-}" = -o ] && [ "\${2-}" = pgid= ] \
  && [ "\${3-}" = -p ] && [ "\${4-}" = "$POST_TERM_RUNNER" ]; then
  case "$post_term_case" in
    unreadable-pgid) [ ! -s "$POST_TERM_SIGNALS" ] || exit 1 ;;
    nonleader) printf '0\n'; exit 0 ;;
  esac
fi
exec "$REAL_PS" "\$@"
SH
  chmod +x "$POST_TERM_BIN/ps"
  post_term_status=0
  post_term_out=$(PATH="$POST_TERM_BIN:$PATH" FM_PROC_ROOT_OVERRIDE="$TMP_ROOT/no-post-term-proc" \
    pe "$HPOST_TERM" retire post-term-src 2>&1) || post_term_status=$?
  case "$post_term_case" in
    mismatch|nonleader)
      assert_absent "$POST_TERM_SIGNALS" "the first signal refuses $post_term_case evidence"
      [ "$post_term_status" -ne 0 ] || fail "retirement escalated despite $post_term_case evidence"
      assert_contains "$post_term_out" "cannot confirm runner identity" \
        "first-signal $post_term_case evidence refuses retirement"
      kill -0 "$POST_TERM_RUNNER" 2>/dev/null \
        || fail "the post-TERM fixture lost its leader instead of exercising $post_term_case evidence"
      kill -0 -"$POST_TERM_RUNNER" 2>/dev/null \
        || fail "a $post_term_case group was killed during escalation"
      assert_present "$HPOST_TERM/state/procevent/post-term-src.source" \
        "first-signal $post_term_case evidence preserves registration"
      assert_present "$FM_PROCEVENT_CLAIM_ROOT/post-term-src.claim" \
        "first-signal $post_term_case evidence preserves its claim"
      kill -KILL -"$POST_TERM_RUNNER" 2>/dev/null || true
      ;;
    *)
      [ -s "$POST_TERM_SIGNALS" ] || fail "the post-TERM fixture never received TERM"
      [ "$post_term_status" -eq 0 ] \
        || fail "retirement abandoned a proved stop after $post_term_case identity: $post_term_out"
      assert_absent "$HPOST_TERM/state/procevent/post-term-src.source" \
        "proved escalation retires the source after $post_term_case identity"
      assert_absent "$FM_PROCEVENT_CLAIM_ROOT/post-term-src.claim" \
        "proved escalation releases its claim after $post_term_case identity"
      ;;
  esac
  for _ in $(seq 1 50); do kill -0 -"$POST_TERM_RUNNER" 2>/dev/null || break; sleep 0.1; done
  kill -0 -"$POST_TERM_RUNNER" 2>/dev/null && fail "the post-TERM fixture group survived: $post_term_case"
  pe "$HPOST_TERM" retire post-term-src >/dev/null
  pass "stop $post_term_case evidence preserves the proved-stop boundary"
done

# --- a crashed runner leader must not make its live child group look stale ---
# The runner is its own process group leader, so SIGKILL on the leader alone
# leaves the blocking source child running in that group. Classifying the
# missing leader as stale would release ownership and start a second poller
# against one canonical source, which for a destructive source means two
# concurrent long polls racing on the same session. The surviving group must be
# stopped before ownership can move.
HG="$TMP_ROOT/hg"; new_home "$HG"
ORPHAN_TRIGGER="$TMP_ROOT/orphan-trigger"
ORPHAN_LOG="$TMP_ROOT/orphan-executions"
ORPHAN_GROUP="$TMP_ROOT/orphan-group"
ORPHAN_OVERLAP="$TMP_ROOT/orphan-overlap"
ORPHAN_BLOCKER="$TMP_ROOT/orphan-blocker.sh"
cat > "$ORPHAN_BLOCKER" <<'SH'
#!/usr/bin/env bash
printf 'started\n' >> "$1"
if [ -s "$3" ]; then
  IFS= read -r old_group < "$3"
  if kill -0 "-$old_group" 2>/dev/null; then
    printf 'overlap\n' > "$4"
  fi
fi
while [ ! -e "$2" ]; do sleep 0.05; done
printf 'orphan result\n'
SH
chmod +x "$ORPHAN_BLOCKER"
pe_register "$HG" lavish orphan-src -- \
  "$ORPHAN_BLOCKER" "$ORPHAN_LOG" "$ORPHAN_TRIGGER" "$ORPHAN_GROUP" "$ORPHAN_OVERLAP" >/dev/null
pe "$HG" reconcile >/dev/null
wait_for "$FM_PROCEVENT_CLAIM_ROOT/orphan-src.claim" || fail "leader-crash fixture never claimed its source"
wait_for "$ORPHAN_LOG" || fail "leader-crash fixture source never started"
orphan_leader=$(sed -n '2p' "$FM_PROCEVENT_CLAIM_ROOT/orphan-src.claim")
case "$orphan_leader" in ''|*[!0-9]*) fail "could not read the runner leader pid: $orphan_leader" ;; esac
printf '%s\n' "$orphan_leader" > "$ORPHAN_GROUP"

kill -KILL "$orphan_leader" 2>/dev/null || fail "could not kill the runner leader"
for _ in $(seq 1 50); do kill -0 "$orphan_leader" 2>/dev/null || break; sleep 0.1; done
kill -0 "$orphan_leader" 2>/dev/null && fail "the runner leader survived SIGKILL"
kill -0 -"$orphan_leader" 2>/dev/null || fail "fixture invalid: the owned child group did not survive the leader"

orphan_out=$(pe "$HG" reconcile)
kill -0 -"$orphan_leader" 2>/dev/null \
  || fail "reconcile signalled an ambiguous leaderless process group: $orphan_out"
assert_contains "$orphan_out" "started=0" \
  "reconcile does not replace an ambiguous leaderless generation"
[ -e "$FM_PROCEVENT_CLAIM_ROOT/orphan-src.claim" ] \
  || fail "refusing ambiguous cleanup must preserve the claim"
[ "$(wc -l < "$ORPHAN_LOG" | tr -d ' ')" = 1 ] \
  || fail "reconcile started a source beside an ambiguous leaderless group"
assert_absent "$ORPHAN_OVERLAP" "no replacement source starts while the leaderless group remains"
kill -KILL -"$orphan_leader" 2>/dev/null || true
for _ in $(seq 1 50); do kill -0 -"$orphan_leader" 2>/dev/null || break; sleep 0.1; done
kill -0 -"$orphan_leader" 2>/dev/null && fail "could not clean up the leaderless fixture group"
pe "$HG" retire orphan-src >/dev/null
pass "an ambiguous leaderless group is preserved without replacement"

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
deadline=$((SECONDS + 60))
while kill -0 -"$GUARD_PID" 2>/dev/null; do
  [ "$SECONDS" -lt "$deadline" ] \
    || fail "the guard left a signal-proof listener's process group running"
  sleep 0.5
done
wait_gone "$GUARD_CHILD" \
  || fail "the guard stopped at the leader and left the signal-proof child running"
[ -s "$TMP_ROOT/proof-guard.signals" ] \
  || fail "the guarded child was never signalled, so nothing about escalation was exercised"
pass "an expired runner's guard escalates past a signal-proof child"

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

