#!/usr/bin/env bash
set -u

PROJECT=/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M1KD55P85JAZN32BH2E2S3PX
. "$PROJECT/tests/wake-helpers.sh"
. "$PROJECT/bin/fm-classify-lib.sh"

WATCH=${WATCH_OVERRIDE:-"$PROJECT/bin/fm-watch.sh"}
DRAIN="$PROJECT/bin/fm-wake-drain.sh"
TMP_ROOT=$(fm_test_tmproot replacement-wait-evidence)
current_pid=

size_of() { LC_ALL=C wc -c < "$1" | tr -d '[:space:]'; }

seen_sig() {
  local reported size ident
  reported=$(status_observed_signature "$1")
  size=$(size_of "$1")
  ident=$(_fm_open_decisions_file_ident "$1")
  printf 'v2\t%s\t%s@%s' "$reported" "$size" "$ident"
}

ack_stopped_cycle() {
  local state=$1 err sequence generation
  err="$state/drain.err"
  FM_STATE_OVERRIDE="$state" "$DRAIN" >/dev/null 2> "$err"
  sequence=$(sed -n 's/^WAKE_ACK_REQUIRED:.*--ack-through \([0-9][0-9]*\) --recovery-generation [A-Za-z0-9._-][A-Za-z0-9._-]*$/\1/p' "$err")
  generation=$(sed -n 's/^WAKE_ACK_REQUIRED:.*--ack-through [0-9][0-9]* --recovery-generation \([A-Za-z0-9._-][A-Za-z0-9._-]*\)$/\1/p' "$err")
  FM_STATE_OVERRIDE="$state" "$DRAIN" --ack-through "$sequence" \
    --recovery-generation "$generation" >/dev/null
}

file_mtime() {
  if [ "$(uname)" = Darwin ]; then stat -f %m "$1" 2>/dev/null; else stat -c %Y "$1" 2>/dev/null; fi
}

wait_poll_cycle() {
  local state=$1 pid=$2 beat first now i=0
  beat="$state/.last-watcher-beat"
  rm -f "$beat"
  first=""
  while [ "$i" -lt 300 ]; do
    kill -0 "$pid" 2>/dev/null || return 1
    first=$(file_mtime "$beat")
    [ -n "$first" ] && break
    sleep 0.1
    i=$((i + 1))
  done
  while [ "$i" -lt 300 ]; do
    kill -0 "$pid" 2>/dev/null || return 1
    now=$(file_mtime "$beat")
    [ -n "$now" ] && [ "$now" != "$first" ] && return 0
    sleep 0.1
    i=$((i + 1))
  done
  return 1
}

reap() { kill "$1" 2>/dev/null || true; wait "$1" 2>/dev/null || true; }

cleanup_evidence() {
  [ -z "$current_pid" ] || reap "$current_pid"
  fm_test_cleanup
}
trap cleanup_evidence EXIT INT TERM

run_case() {
  local label initial replacement expected dir state fakebin out pane statusf window key sig back pid wakes
  label=$1
  initial=$2
  replacement=$3
  expected=$4
  dir=$(make_case "$label")
  state="$dir/state"
  fakebin="$dir/fakebin"
  out="$dir/watcher.out"
  pane="$dir/pane.txt"
  statusf="$state/held.status"
  window="test:fm-held"
  key=$(printf '%s' "$window" | tr ':/.' '___')

  printf 'idle after first wait\n' > "$pane"
  printf 'window=%s\nkind=ship\nharness=grok\nbackend=tmux\n' "$window" > "$state/held.meta"
  printf '%s\n' "$initial" > "$statusf"
  back=$(( $(date +%s) - 120 ))
  if [ "$(uname)" = Darwin ]; then touch -mt "$(date -r "$back" '+%Y%m%d%H%M.%S')" "$statusf"; else touch -m -d "@$back" "$statusf"; fi
  sig=$(seen_sig "$statusf")
  printf '%s' "$sig" > "$state/.seen-held_status"
  printf '%s' "$(hash_text 'idle after first wait')" > "$state/.hash-$key"
  printf '1\n' > "$state/.count-$key"

  PATH="$fakebin:$PATH" FM_FAKE_TMUX_WINDOW="$window" FM_FAKE_TMUX_CAPTURE="$pane" \
    FM_FAKE_TMUX_CURRENT_COMMAND=zsh FM_FAKE_CREW_STATE='state: stopped · source: pane · bare shell' \
    FM_STATE_OVERRIDE="$state" FM_CREW_STATE_BIN="$fakebin/fm-crew-state.sh" \
    FM_PAUSE_RESURFACE_SECS=30 FM_POLL=1 FM_SIGNAL_GRACE=1 \
    FM_CHECK_INTERVAL=999999 FM_HEARTBEAT=999999 "$WATCH" > "$out" &
  pid=$!
  current_pid=$pid
  wait_for_exit "$pid" 100 || { printf 'ERROR: initial wait did not surface\n' >&2; return 1; }
  current_pid=
  ack_stopped_cycle "$state" || { printf 'ERROR: initial notification could not be acknowledged\n' >&2; return 1; }

  printf '%s\n' "$replacement" >> "$statusf"
  sig=$(seen_sig "$statusf")
  printf '%s' "$sig" > "$state/.seen-held_status"
  printf 'idle after replacement wait\n' > "$pane"
  PATH="$fakebin:$PATH" FM_FAKE_TMUX_WINDOW="$window" FM_FAKE_TMUX_CAPTURE="$pane" \
    FM_FAKE_TMUX_CURRENT_COMMAND=zsh FM_FAKE_CREW_STATE='state: stopped · source: pane · bare shell' \
    FM_WATCH_HANDLING_SUCCESSOR=1 FM_STATE_OVERRIDE="$state" \
    FM_CREW_STATE_BIN="$fakebin/fm-crew-state.sh" FM_PAUSE_RESURFACE_SECS=30 \
    FM_POLL=1 FM_SIGNAL_GRACE=1 FM_CHECK_INTERVAL=999999 FM_HEARTBEAT=999999 "$WATCH" >> "$out" &
  pid=$!
  current_pid=$pid
  wait_poll_cycle "$state" "$pid" || { printf 'ERROR: fresh replacement exited during its first completed cycle\n' >&2; return 1; }
  wait_poll_cycle "$state" "$pid" || { printf 'ERROR: fresh replacement exited during its second completed cycle\n' >&2; return 1; }
  reap "$pid"
  current_pid=
  wakes=$(awk -F '\t' -v w="$window" '$3 == "stale" && $4 == w { n++ } END { print n + 0 }' "$state/.wake-queue" 2>/dev/null || echo 0)

  printf 'CASE %s\n' "$label"
  printf 'fresh replacement survived completed watcher cycles: yes\n'
  printf 'fresh replacement queued rechecks: %s\n' "$wakes"

  back=$(( $(date +%s) - 120 ))
  if [ "$(uname)" = Darwin ]; then touch -mt "$(date -r "$back" '+%Y%m%d%H%M.%S')" "$statusf"; else touch -m -d "@$back" "$statusf"; fi
  sig=$(seen_sig "$statusf")
  printf '%s' "$sig" > "$state/.seen-held_status"
  PATH="$fakebin:$PATH" FM_FAKE_TMUX_WINDOW="$window" FM_FAKE_TMUX_CAPTURE="$pane" \
    FM_FAKE_TMUX_CURRENT_COMMAND=zsh FM_FAKE_CREW_STATE='state: stopped · source: pane · bare shell' \
    FM_WATCH_HANDLING_SUCCESSOR=1 FM_STATE_OVERRIDE="$state" \
    FM_CREW_STATE_BIN="$fakebin/fm-crew-state.sh" FM_PAUSE_RESURFACE_SECS=30 \
    FM_POLL=1 FM_SIGNAL_GRACE=1 FM_CHECK_INTERVAL=999999 FM_HEARTBEAT=999999 "$WATCH" >> "$out" &
  pid=$!
  current_pid=$pid
  wait_for_exit "$pid" 100 || { printf 'ERROR: aged replacement did not re-surface\n' >&2; return 1; }
  current_pid=
  wakes=$(awk -F '\t' -v w="$window" '$3 == "stale" && $4 == w { n++ } END { print n + 0 }' "$state/.wake-queue" 2>/dev/null || echo 0)
  printf 'aged replacement queued rechecks: %s\n' "$wakes"
  printf 'aged replacement notification: '
  awk -F '\t' -v w="$window" '$3 == "stale" && $4 == w { print $5 }' "$state/.wake-queue"
  grep -F "$expected" "$state/.wake-queue" >/dev/null
  printf '\n'
}

run_case paused \
  'paused: waiting on validation run one' \
  'paused: waiting on validation run two' \
  'awaiting external' || exit 1
run_case captain-held \
  'captain-held [key=route]: awaiting the routing call' \
  'captain-held [key=release]: awaiting the release call' \
  'awaiting the captain' || exit 1
