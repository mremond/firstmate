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
printf '%s\n' "$$" > "$FM_HOME/state/.lock"
"$ROOT/bin/fm-wake-drain.sh" > "$EVIDENCE/watcher-drain.log" 2>&1
python3 - "$ROOT" "$EVIDENCE" <<'ACK'
import pathlib,re,subprocess,sys
root,evidence=map(pathlib.Path,sys.argv[1:])
text=(evidence/'watcher-drain.log').read_text()
m=re.search(r'WAKE_ACK_REQUIRED:.*--ack-through ([0-9]+) --recovery-generation ([A-Za-z0-9._:-]+)',text)
assert m,text
with (evidence/'watcher-ack.log').open('w') as f:
 subprocess.run([str(root/'bin/fm-wake-drain.sh'),'--ack-through',m[1],'--recovery-generation',m[2]],stdout=f,stderr=subprocess.STDOUT,check=True)
ACK
fm_pr_poll_artifacts_valid "$FM_HOME/state" "$ID" "$ROOT/bin/fm-pr-poll.sh"
FM_CHECK_INTERVAL=0 FM_POLL=1 FM_SIGNAL_GRACE=0 python3 - "$ROOT/bin/fm-watch.sh" "$EVIDENCE/watcher-merged.log" <<'WATCH'
import subprocess,sys
with open(sys.argv[2],'w') as f:
 r=subprocess.run(['bash',sys.argv[1]],stdout=f,stderr=subprocess.STDOUT,timeout=150)
raise SystemExit(r.returncode)
WATCH
cat "$EVIDENCE/watcher-merged.log"
grep -F "$ID.check.sh: merged" "$EVIDENCE/watcher-merged.log"
[ ! -e "$FM_HOME/state/$ID.check.sh" ]
cp "$FM_HOME/state/$ID.pr-poll-merge-notified" "$EVIDENCE/merge-notified.txt"
echo 'MERGE_ANNOUNCED after real relaunch; authenticated poll retired'
