#!/usr/bin/env bash
set -euo pipefail
ROOT=$PWD
SCRATCH="$ROOT/.test-relaunch-validation"
EVIDENCE=/Users/mremond/.no-mistakes/evidence/01M35D1FABR2MDF1PE89WW96B2
SESSION=$(cat "$SCRATCH/session")
ID=$(cat "$SCRATCH/task-id")
PANE=$(cat "$SCRATCH/pane")
ORIGINAL_PATH=$PATH
LAB_HELPER="$ROOT/bin/fm-herdr-lab.sh"
export FM_HERDR_LAB_STATE_DIR="$SCRATCH/lab-state"
export FM_HOME="$SCRATCH/home" FM_ROOT_OVERRIDE="$ROOT" CLAUDE_CONFIG_DIR="$SCRATCH/claude-config"
export FM_SPAWN_NO_GUARD=1 FM_GATE_REFUSE_BYPASS=1
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
unset HERDR_ENV HERDR_PANE_ID HERDR_TAB_ID HERDR_WORKSPACE_ID HERDR_SOCKET_PATH TMUX TMUX_PANE TASKS_AXI_FILE TASKS_AXI_BACKEND
export HERDR_SESSION="$SESSION" PATH="$SCRATCH/lab-bin:$ORIGINAL_PATH"
export FM_CONTROL_LAUNCH_WAIT=120 FM_CONTROL_EXIT_WAIT=60 FM_CONTROL_POLL=0.5
. "$ROOT/bin/fm-pr-lib.sh"
. "$ROOT/bin/fm-trace-context-lib.sh"
lab() { env PATH="$ORIGINAL_PATH" "$LAB_HELPER" run "$SESSION" "$@"; }
wait_ready() {
  for attempt in $(seq 1 90); do
    lab agent get "$PANE" > "$SCRATCH/agent-current.json" 2>/dev/null || true
    state=$(jq -r '.result.agent.agent_status // empty' "$SCRATCH/agent-current.json")
    if [ "$state" = idle ] || [ "$state" = done ]; then
      lab pane read "$PANE" --source recent --lines 75 > "$EVIDENCE/pane-$1.txt"
      if grep -q 'LAB_READY' "$EVIDENCE/pane-$1.txt" && [ -e "$FM_HOME/state/$ID.turn-ended" ]; then
        cp "$SCRATCH/agent-current.json" "$EVIDENCE/agent-$1.json"
        return 0
      fi
    fi
    sleep 1
  done
  lab pane read "$PANE" --source recent --lines 100 > "$EVIDENCE/pane-$1.txt"
  echo "READY_TIMEOUT $1 state=$state"
  return 1
}
wait_ready initial
URL=$(jq -r '.[0].url' "$EVIDENCE/observed-merged-pr.json")
printf '%s\n' "$$" > "$FM_HOME/state/.lock"
FM_TRACE_CONTEXT=off fm_trace_context_session_start "$FM_HOME/config" "$FM_HOME/state/.trace-context-effective"
"$ROOT/bin/fm-pr-check.sh" "$ID" "$URL"
fm_pr_poll_artifacts_valid "$FM_HOME/state" "$ID" "$ROOT/bin/fm-pr-poll.sh"
echo "ARMED_AUTHENTICATED task=$ID url=$URL"
for suffix in check.sh pr-poll pr-poll-registration; do
  cp "$FM_HOME/state/$ID.$suffix" "$SCRATCH/original-$suffix"
done
previous_traceparent=
for scenario in control-off control-on control-on-repeat spawn-on spawn-off; do
  case "$scenario" in *off) trace=off ;; *) trace=on ;; esac
  FM_TRACE_CONTEXT="$trace" fm_trace_context_session_start "$FM_HOME/config" "$FM_HOME/state/.trace-context-effective"
  printf '\nSCENARIO %s\n' "$scenario"
  case "$scenario" in
    control-*) "$ROOT/bin/fm-control.sh" "$ID" relaunch --note 'Lifecycle validation only. Reply exactly LAB_READY, use no tools, and wait.' ;;
    spawn-*)
      "$ROOT/bin/fm-control.sh" "$ID" exit
      "$ROOT/bin/fm-spawn.sh" "$ID" --relaunch
      ;;
  esac
  wait_ready "$scenario"
  fm_pr_poll_artifacts_valid "$FM_HOME/state" "$ID" "$ROOT/bin/fm-pr-poll.sh"
  for suffix in check.sh pr-poll pr-poll-registration; do
    cmp "$FM_HOME/state/$ID.$suffix" "$SCRATCH/original-$suffix"
  done
  [ "$(sed -n 's/^window=//p' "$FM_HOME/state/$ID.meta")" = "$SESSION:$PANE" ]
  cp "$FM_HOME/state/$ID.meta" "$EVIDENCE/meta-$scenario.txt"
  traceparent=$(sed -n 's/^traceparent=//p' "$FM_HOME/state/$ID.meta")
  if [ "$trace" = on ]; then
    fm_trace_context_valid "$traceparent"
    [ -z "$previous_traceparent" ] || [ "$traceparent" = "$previous_traceparent" ]
    previous_traceparent=$traceparent
  else
    [ -z "$traceparent" ]
  fi
  echo "RELAUNCH_AUTHENTICATED $scenario traceparent=${traceparent:-disabled}"
done
cp "$FM_HOME/state/$ID.meta" "$SCRATCH/valid.meta"
printf 'unrecognized=1\n' >> "$FM_HOME/state/$ID.meta"
if fm_pr_poll_artifacts_valid "$FM_HOME/state" "$ID" "$ROOT/bin/fm-pr-poll.sh"; then
  echo 'ERROR: tampered metadata was accepted'
  exit 1
fi
echo 'TAMPER_REJECTED unexpected trailing metadata key'
run_watcher() {
  FM_CHECK_INTERVAL=0 FM_POLL=1 FM_SIGNAL_GRACE=0 python3 - "$ROOT/bin/fm-watch.sh" "$EVIDENCE/watcher-$1.log" <<'PY'
import subprocess,sys
with open(sys.argv[2],'w') as f:
  result=subprocess.run(['bash',sys.argv[1]],stdout=f,stderr=subprocess.STDOUT,timeout=150)
raise SystemExit(result.returncode)
PY
}
run_watcher tampered
grep -F 'rejected unauthenticated state checks' "$EVIDENCE/watcher-tampered.log"
cp "$SCRATCH/valid.meta" "$FM_HOME/state/$ID.meta"
fm_pr_poll_artifacts_valid "$FM_HOME/state" "$ID" "$ROOT/bin/fm-pr-poll.sh"
run_watcher merged
cat "$EVIDENCE/watcher-merged.log"
grep -F "$ID.check.sh: merged" "$EVIDENCE/watcher-merged.log"
[ ! -e "$FM_HOME/state/$ID.check.sh" ]
cp "$FM_HOME/state/$ID.pr-poll-merge-notified" "$EVIDENCE/merge-notified.txt"
echo 'MERGE_ANNOUNCED after real relaunch; authenticated poll retired'
