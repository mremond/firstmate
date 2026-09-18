#!/usr/bin/env bash
# Live drive: the REAL bin/fm-watch.sh + REAL bin/fm-crew-state.sh against a REAL
# tmux server (isolated via TMUX_TMPDIR), one scout window whose pane is an idle
# shell (dead agent -> absorbed declared-wait cadence) or a process named `grok`
# (live agent -> surface path). Test helpers are sourced only for state
# bookkeeping (seen signatures, mtimes, wake-queue acks).
# Usage: live-tmux-note-wait.sh <worktree-root> <shell|grok>
set -u
WT=$1; MODE=$2
cd "$WT" || exit 1
. tests/wake-helpers.sh
. bin/fm-classify-lib.sh
eval "$(sed -n '/^seen_sig() {/,/^}/p;/^size_of() {/,/^}/p;/^set_mtime() {/,/^}/p;/^ack_stopped_cycle() {/,/^}/p' tests/fm-watch-triage.test.sh)"
DRAIN="$WT/bin/fm-wake-drain.sh"
WATCH="$WT/bin/fm-watch.sh"

T=$(mktemp -d /tmp/fm-live-note.XXXX)
export TMUX_TMPDIR="$T/tmuxsock"; mkdir -p "$TMUX_TMPDIR"; unset TMUX
state="$T/state"; mkdir -p "$state" "$T/wt"
window=live:fm-noted; key=live_fm-noted
if [ "$MODE" = grok ]; then
  cp "$(readlink -f /opt/homebrew/bin/jq)" "$T/grok"; cmd="$T/grok -R ."  # a live agent process named grok
else
  cmd="env -i PATH=/usr/bin:/bin PS1='$ ' /bin/bash --norc --noprofile"
fi
tmux new-session -d -s live -n fm-noted -x 120 -y 30 "$cmd"
sleep 1
echo "pane_current_command: $(tmux display-message -p -t "$window" '#{pane_current_command}')"

pane() {  # replace visible pane content with <text>
  if [ "$MODE" = grok ]; then tmux send-keys -t "$window" "$1" Enter
  else tmux send-keys -t "$window" "clear; echo '$1'" Enter; fi
  sleep 0.5
}
stale_wakes() { awk -F '\t' -v w="$window" '$3=="stale" && $4==w{n++} END{print n+0}' "$state/.wake-queue" 2>/dev/null || echo 0; }
write_status() { local l; for l in "$@"; do printf '%s\n' "$l" >> "$state/noted.status"; echo "  status += $l"; done
  printf '%s' "$(seen_sig "$state/noted.status")" > "$state/.seen-noted_status"; }
round() {  # <label> ; runs watcher up to 12s; prints SURFACED / ABSORBED
  local pid i=0
  FM_STATE_OVERRIDE="$state" FM_CREW_STATE_BIN="$WT/bin/fm-crew-state.sh" FM_WATCH_HANDLING_SUCCESSOR=1 \
    FM_PAUSE_RESURFACE_SECS=240 FM_POLL=1 FM_SIGNAL_GRACE=1 FM_CHECK_INTERVAL=999999 FM_HEARTBEAT=999999 \
    "$WATCH" >> "$T/watch.out" 2>>"$T/watch.err" &
  pid=$!
  while [ $i -lt 120 ] && kill -0 $pid 2>/dev/null; do sleep 0.1; i=$((i+1)); done
  if kill -0 $pid 2>/dev/null; then kill $pid; wait $pid 2>/dev/null; echo "  -> ABSORBED (watcher still running after 12s); stale wakes queued=$(stale_wakes)"
  else wait $pid; echo "  -> SURFACED (watcher exited): $(tail -1 "$T/watch.out")"; echo "     stale wakes queued=$(stale_wakes)"; fi
}

printf 'window=%s\nkind=scout\nharness=grok\nbackend=tmux\nworktree=%s\n' "$window" "$T/wt" > "$state/noted.meta"
DECL=${DECL:-'paused: waiting on validation run one'}
CHANGED=${CHANGED:-'paused: waiting on validation run two'}
echo "== 0. declare the wait: $DECL"
printf '%s\n' "$DECL" > "$state/noted.status"
set_mtime "$(( $(date +%s) - 500 ))" "$state/noted.status"
printf '%s' "$(seen_sig "$state/noted.status")" > "$state/.seen-noted_status"
pane 'idle on the wait'
round; ack_stopped_cycle "$state" >/dev/null || echo "  (ack failed)"

echo "== 1. note: under the live wait (expect ABSORBED, 0 new stale wakes)"
write_status 'note: CI queue is long today, nothing to do yet'
pane 'idle after the note'
round
echo "   last_status_line=[$(last_status_line "$state/noted.status")] status_wait_line=[$(status_wait_line "$state/noted.status")]"

echo "== 2. cadence elapses (backdate .paused-resurfaced) -> expect one recheck, age >= 500s"
set_mtime "$(( $(date +%s) - 2000 ))" "$state/.paused-resurfaced-$key" 2>/dev/null || echo "  (no .paused-resurfaced marker)"
pane 'idle once the cadence elapsed'
round; grep stale "$state/.wake-queue" | tail -1 | cut -f5-; ack_stopped_cycle "$state" >/dev/null || echo "  (ack failed)"

echo "== 3. changed declaration followed by a note: -> expect SURFACED at once"
write_status "$CHANGED" 'note: the release call replaced the routing call'
pane 'idle after the changed declaration'
round; ack_stopped_cycle "$state" >/dev/null || echo "  (ack failed)"

echo "== 4. worker leaves the wait (working:), then a note: -> expect SURFACED as before"
write_status 'working: validation finished, back on the task' 'note: picking the next step'
pane 'idle after leaving the wait'
round
echo "   pause tracking marker present? $([ -e "$state/.paused-$key" ] && echo yes || echo no)"
echo "== wake queue"; cat "$state/.wake-queue" 2>/dev/null
tmux kill-server 2>/dev/null; rm -rf "$T"
