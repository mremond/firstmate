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
. "$NM_TEST_CODE_ROOT/tests/lib.sh"

ROOT=$NM_TEST_CODE_ROOT
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

# When the post-TERM cases fail they must say WHAT THEY SAW, not only that they
# failed. This assertion has failed in CI and passed in every environment
# available here, so the only instrument that reproduces it is the one we cannot
# attach a debugger to. An assertion this change reworked which fails without
# evidence is a defect in the change, not bad luck, so the evidence is collected
# on the failure path only and costs nothing when the case passes.
post_term_evidence() {  # <case> <runner-pid> <claim> <signals> <started-epoch> <retire-output>
  local case=$1 runner=$2 claim=$3 signals=$4 started=$5 out=$6
  {
    printf 'post-TERM evidence (%s case)\n' "$case"
    printf '  elapsed since retire started: %ss\n' "$(( $(date +%s) - started ))"
    printf '  identity recorded at claim time: %s\n' "$(sed -n '4p' "$claim" 2>/dev/null || echo '<claim unreadable>')"
    printf '  identity readable now (real ps): %s\n' "$(LC_ALL=C ps -p "$runner" -o lstart= 2>/dev/null || echo '<ps failed>')"
    printf '  signals file: %s (%s bytes)\n' "$signals" "$(wc -c < "$signals" 2>/dev/null | tr -d ' ' || echo 0)"
    printf '  leader state: %s\n' "$(ps -o pid=,ppid=,pgid=,stat= -p "$runner" 2>/dev/null || echo '<leader gone>')"
    printf '  leader wchan: %s\n' "$(ps -o wchan= -p "$runner" 2>/dev/null || echo '<none>')"
    printf '  live members of the runner group:\n'
    ps -Ao pid,ppid,pgid,stat,wchan,command 2>/dev/null | awk -v g="$runner" 'NR==1 || $3==g' | sed 's/^/    /'
    printf '  retire said: %s\n' "${out:-<no output>}"
  } >&2
}

for post_term_case in mismatch; do
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
  # The child can publish its PID before startup releases the source lock.
  # Cross that boundary before suspending the runner, or retirement waits on
  # a stopped lock owner instead of exercising the signal checks below.
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
  post_term_started=$(date +%s)
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
      if [ ! -s "$POST_TERM_SIGNALS" ]; then
        post_term_evidence "$post_term_case" "$POST_TERM_RUNNER" \
          "$FM_PROCEVENT_CLAIM_ROOT/post-term-src.claim" "$POST_TERM_SIGNALS" \
          "$post_term_started" "$post_term_out"
        fail "the post-TERM fixture never received TERM"
      fi
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

