#!/usr/bin/env bash
set -euo pipefail
ROOT=$PWD
SCRATCH="$ROOT/.test-relaunch-validation"
EVIDENCE=/Users/mremond/.no-mistakes/evidence/01M35D1FABR2MDF1PE89WW96B2
ORIGINAL_PATH=$PATH
LAB_HELPER="$ROOT/bin/fm-herdr-lab.sh"
SESSION=$(cat "$SCRATCH/session")
export FM_HERDR_LAB_STATE_DIR="$SCRATCH/lab-state"
export FM_HOME="$SCRATCH/home" FM_ROOT_OVERRIDE="$ROOT"
export CLAUDE_CONFIG_DIR="$SCRATCH/claude-config"
export FM_SPAWN_NO_GUARD=1 FM_GATE_REFUSE_BYPASS=1
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
unset HERDR_ENV HERDR_PANE_ID HERDR_TAB_ID HERDR_WORKSPACE_ID HERDR_SOCKET_PATH TMUX TMUX_PANE TASKS_AXI_FILE TASKS_AXI_BACKEND
export HERDR_SESSION="$SESSION"
cleanup() {
  local rc=$?
  trap - EXIT
  env PATH="$ORIGINAL_PATH" "$LAB_HELPER" teardown "$SESSION" >> "$EVIDENCE/lab-lifecycle.log" 2>&1 || rc=1
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' INT TERM
env PATH="$ORIGINAL_PATH" "$LAB_HELPER" provision "$SESSION"
mkdir -p "$SCRATCH/lab-bin" "$FM_HOME/state" "$FM_HOME/data" "$FM_HOME/config" "$SCRATCH/project"
printf 'auto\n' > "$FM_HOME/config/claude-permission-mode"
printf 'off\n' > "$FM_HOME/config/herdr-presentation-spaces"
cat > "$SCRATCH/lab-bin/herdr" <<EOF
#!/usr/bin/env bash
set -eu
args=("\$@")
n=\${#args[@]}
if [ "\$n" -ge 2 ] && [ "\${args[\$((n-2))]}" = --session ] && [ "\${args[\$((n-1))]}" = "$SESSION" ]; then
  args=("\${args[@]:0:\$((n-2))}")
else
  echo 'refused non-lab Herdr request' >&2
  exit 97
fi
exec env PATH='$ORIGINAL_PATH' '$LAB_HELPER' run '$SESSION' "\${args[@]}"
EOF
chmod +x "$SCRATCH/lab-bin/herdr"
lab() { env PATH="$ORIGINAL_PATH" "$LAB_HELPER" run "$SESSION" "$@"; }
if [ ! -d "$SCRATCH/project/.git" ]; then
git -C "$SCRATCH/project" init -q
printf '# Relaunch live validation scratch project\n' > "$SCRATCH/project/README.md"
git -C "$SCRATCH/project" add README.md
git -C "$SCRATCH/project" -c user.name='Firstmate Validation' -c user.email=validation@example.invalid commit -qm initial
git -C "$SCRATCH/project" worktree add --quiet -b lab-poll "$SCRATCH/task"
fi
ID="nmpoll${RANDOM}"
printf '%s\n' "$ID" > "$SCRATCH/task-id"
"$ROOT/bin/fm-brief.sh" "$ID" lab-poll --mode local-only --herdr-lab
python3 - "$FM_HOME/data/$ID/brief.md" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1])
s=p.read_text().replace('{TASK}', 'Participate in an isolated lifecycle verification. Reply exactly LAB_READY and wait. Do not use any tools, edit files, publish, commit, merge, or run any pipeline.')
s=s.replace('{FIRSTMATE_SPEC}', 'This task only supplies a real idle agent for the parent tester to stop and relaunch. Do not perform the generic implementation or delivery steps below. Reply LAB_READY, then wait without tools.')
p.write_text(s)
PY
WS=$(lab workspace create --cwd "$SCRATCH/task" --label pr-poll-relaunch-validation --no-focus)
printf '%s\n' "$WS" > "$EVIDENCE/lab-workspace.json"
PANE=$(printf '%s' "$WS" | jq -er '.result.root_pane.pane_id')
WORKSPACE=$(printf '%s' "$WS" | jq -er '.result.workspace.workspace_id')
TAB=$(printf '%s' "$WS" | jq -er '.result.tab.tab_id')
printf '%s\n' "$PANE" > "$SCRATCH/pane"
cat > "$FM_HOME/state/$ID.meta" <<EOF
window=$SESSION:$PANE
endpoint_task_id=$ID
worktree=$SCRATCH/task
project=$SCRATCH/project
harness=codex
kind=ship
mode=local-only
yolo=off
model=default
effort=default
backend=herdr
herdr_session=$SESSION
herdr_workspace_id=$WORKSPACE
herdr_tab_id=$TAB
herdr_pane_id=$PANE
EOF
chmod 600 "$FM_HOME/state/$ID.meta"
printf -v CMD 'export CODEX_HOME=%q; stty rows 40 cols 120' "$SCRATCH/codex-config"
lab pane run "$PANE" "$CMD"
env PATH="$ORIGINAL_PATH" "$LAB_HELPER" viewer start "$SESSION"
export PATH="$SCRATCH/lab-bin:$ORIGINAL_PATH"
"$ROOT/bin/fm-spawn.sh" "$ID" --relaunch
printf 'INITIAL_LAUNCH task=%s session=%s pane=%s\n' "$ID" "$SESSION" "$PANE"
while [ ! -e "$SCRATCH/stop-lab" ]; do sleep 1; done
