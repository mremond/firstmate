#!/usr/bin/env bash
# Live drive: real bin/fm-watch.sh + real fm-crew-state.sh + real fm-wake-drain.sh
# against a REAL tmux server on a private socket. Usage: <repo-root> <paused|held> <zsh|grok>
set -u
ROOT=$1 MODE=$2 CMD=$3
REAL_TMUX=$(command -v tmux)
W=$(mktemp -d "${TMPDIR:-/tmp}/fm-live-note.XXXXXX")
SOCK="fm-live-note-$$"
STATE="$W/state"; mkdir -p "$STATE" "$W/bin" "$W/wt" "$W/pane"
cleanup() { "$REAL_TMUX" -L "$SOCK" kill-server >/dev/null 2>&1; rm -rf "$W"; }
trap cleanup EXIT
printf '#!/usr/bin/env bash\nexec "%s" -L "%s" "$@"\n' "$REAL_TMUX" "$SOCK" > "$W/bin/tmux"; chmod +x "$W/bin/tmux"
if [ "$CMD" = zsh ]; then PANE_CMD="env PS1=%# /bin/zsh -f"; else printf '#include <stdio.h>\nint main(void){char b[512];while(fgets(b,sizeof b,stdin)){fputs(b,stdout);fflush(stdout);}return 0;}\n' > "$W/e.c"; cc -o "$W/pane/grok" "$W/e.c"; PANE_CMD="$W/pane/grok"; fi         # pane process whose name is $CMD (zsh = dead agent, grok = live harness)
export PATH="$W/bin:$PATH"
. "$ROOT/bin/fm-classify-lib.sh"
size_of() { LC_ALL=C wc -c < "$1" | tr -d '[:space:]'; }
seen_sig() { printf 'v2\t%s\t%s@%s' "$(status_observed_signature "$1")" "$(size_of "$1")" "$(_fm_open_decisions_file_ident "$1")"; }
prime() { printf '%s' "$(seen_sig "$STATE/noted.status")" > "$STATE/.seen-noted_status"; }
if [ "$MODE" = paused ]; then
  DECL='paused: waiting on validation run one'; CHANGED='paused: waiting on validation run two'
else
  DECL='captain-held [key=route]: awaiting the routing call'; CHANGED='captain-held [key=route]: awaiting the release call'
fi
WIN="live:fm-noted"; KEY=live_fm-noted
tmux new-session -d -s live -n fm-noted -x 120 -y 30 "$PANE_CMD"
sleep 0.5
echo "tmux pane_current_command: $(tmux display-message -p -t "$WIN" '#{pane_current_command}')"
printf 'window=%s\nkind=scout\nharness=grok\nbackend=tmux\nworktree=%s\n' "$WIN" "$W/wt" > "$STATE/noted.meta"
printf '%s\n' "$DECL" > "$STATE/noted.status"
touch -t "$(date -r $(( $(date +%s) - 500 )) +%Y%m%d%H%M.%S)" "$STATE/noted.status"
prime
say() { tmux send-keys -t "$WIN" -l "$1"; tmux send-keys -t "$WIN" Enter; sleep 0.3; }
ack() {
  local err="$W/drain.err" seq gen
  FM_STATE_OVERRIDE="$STATE" "$ROOT/bin/fm-wake-drain.sh" >"$W/drain.out" 2>"$err" || true
  echo "  drained: $(tr '\n' ' ' < "$W/drain.out")"
  seq=$(sed -n 's/^WAKE_ACK_REQUIRED:.*--ack-through \([0-9]*\) --recovery-generation .*/\1/p' "$err")
  gen=$(sed -n 's/^WAKE_ACK_REQUIRED:.*--recovery-generation \([A-Za-z0-9._-]*\)$/\1/p' "$err")
  [ -n "$seq" ] && FM_STATE_OVERRIDE="$STATE" "$ROOT/bin/fm-wake-drain.sh" --ack-through "$seq" --recovery-generation "$gen" >/dev/null 2>&1
}
# Run the watcher up to <secs>; print how it ended.
round() {  # <label> <secs>
  local label=$1 secs=$2 pid t=0
  FM_STATE_OVERRIDE="$STATE" FM_CREW_STATE_BIN="$ROOT/bin/fm-crew-state.sh" FM_WATCH_HANDLING_SUCCESSOR=1 \
    FM_PAUSE_RESURFACE_SECS=${RESURF:-45} FM_POLL=1 FM_SIGNAL_GRACE=1 FM_CHECK_INTERVAL=999999 FM_HEARTBEAT=999999 \
    "$ROOT/bin/fm-watch.sh" > "$W/watch.out" 2>&1 &
  pid=$!
  while [ "$t" -lt "$secs" ] && kill -0 "$pid" 2>/dev/null; do sleep 1; t=$((t+1)); done
  if kill -0 "$pid" 2>/dev/null; then kill "$pid"; wait "$pid" 2>/dev/null; echo "[$label] watcher stayed quiet for ${secs}s (no wake)"
  else wait "$pid"; echo "[$label] watcher WOKE after ~${t}s: $(tr '\n' ' ' < "$W/watch.out")"; fi
  echo "  queue: $(cut -f3- "$STATE/.wake-queue" 2>/dev/null | tr '\n' '|')"
}
echo "=== MODE=$MODE pane=$CMD  declaration: $DECL"
say "idle on the wait"
round "1 first sight of declared wait" 20; ack
START=$(date +%s)
echo "--- appending: note: upstream PR merged and its checks green, waiting for the tag"
printf '%s\n' 'note: upstream PR merged and its checks green, waiting for the tag' >> "$STATE/noted.status"
say "idle after the note"
round "2a note: status write (first-class event)" 20; ack
round "2b note under live wait, before cadence" 15
echo "  latest event (last_status_line): $(last_status_line "$STATE/noted.status")"
echo "  wait in force (status_wait_line): $(status_wait_line "$STATE/noted.status")"
rem=$(( ${RESURF:-45} - ($(date +%s) - START) ))
round "3 cadence elapses (resurface secs ${RESURF:-45})" $(( rem > 0 ? rem + 25 : 25 )); ack
echo "--- appending changed declaration + note: $CHANGED"
printf '%s\n%s\n' "$CHANGED" 'note: the release call replaced the routing call' >> "$STATE/noted.status"; prime
say "idle after the changed declaration"
round "4 changed declaration" 20; ack
echo "--- appending: working: validation finished, back on the task / note: picking the next step"
printf '%s\n%s\n' 'working: validation finished, back on the task' 'note: picking the next step' >> "$STATE/noted.status"; prime
say "idle after leaving the wait"
round "5 note after genuinely leaving the wait" 20; ack
echo "  .paused-$KEY present after leaving: $([ -e "$STATE/.paused-$KEY" ] && echo yes || echo no)"
