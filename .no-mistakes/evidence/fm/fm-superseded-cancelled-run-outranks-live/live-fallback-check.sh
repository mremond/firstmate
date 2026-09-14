#!/usr/bin/env bash
set -euo pipefail
root=/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2GV0N1CJ7TGNYN3P76KK9TS
cd "$root"
live_root="$root/.test-3215/live"
socket="$root/.t3215"
mkdir -p "$live_root/state"
test ! -e "$socket"
trap 'tmux -S "$socket" kill-server 2>/dev/null || true' EXIT
tmux -S "$socket" -f /dev/null new-session -d -s nm3215 -n worker -c "$root" /bin/sh
export TMUX="$socket,0,0"
export FM_HOME="$live_root"
export FM_STATE_OVERRIDE="$live_root/state"
printf 'worktree=%s\nkind=ship\nharness=claude\nbackend=tmux\nwindow=nm3215:worker\n' "$root" > "$live_root/state/worker.meta"
printf 'working: implementation continues without a gate\n' > "$live_root/state/worker.status"
printf '$ no-mistakes axi status\n'
set +e
no-mistakes axi status
status_rc=$?
set -e
printf 'exit: %s\n' "$status_rc"
printf '$ tmux list-windows -t nm3215\n'
tmux list-windows -t nm3215 -F '#{session_name}:#{window_name} #{pane_current_command}'
printf '$ bin/fm-busy-event.sh arm <isolated-state> worker\n'
gen=$(bin/fm-busy-event.sh arm "$live_root/state" worker)
printf '$ bin/fm-busy-event.sh apply <isolated-state> worker busy --gen <generation> --source claude-hook --event user-prompt-submit\n'
bin/fm-busy-event.sh apply "$live_root/state" worker busy --gen "$gen" --source claude-hook --event user-prompt-submit
printf '$ bin/fm-crew-state.sh worker\n'
busy=$(bin/fm-crew-state.sh worker)
printf '%s\n' "$busy"
case "$busy" in 'state: working · source: pane · harness busy ('*) ;; *) exit 1 ;; esac
printf '$ bin/fm-busy-event.sh apply <isolated-state> worker idle --gen <generation> --source claude-hook --event stop\n'
bin/fm-busy-event.sh apply "$live_root/state" worker idle --gen "$gen" --source claude-hook --event stop
printf '$ bin/fm-crew-state.sh worker\n'
idle=$(bin/fm-crew-state.sh worker)
printf '%s\n' "$idle"
case "$idle" in 'state: working · source: status-log · implementation continues without a gate') ;; *) exit 1 ;; esac
printf '$ bin/fm-busy-event.sh retire <isolated-state> worker --gen <generation>\n'
bin/fm-busy-event.sh retire "$live_root/state" worker --gen "$gen"
