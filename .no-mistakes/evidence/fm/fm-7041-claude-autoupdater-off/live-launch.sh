#!/bin/bash
set -eu
ROOT=$PWD
E=/Users/mremond/.no-mistakes/evidence/01M4R0VBX5J31ZB93BX9BA81C3
LAB=$(mktemp -d "${TMPDIR:-/tmp}/fm-lab.XXXXXX")
bin/fm-lab-home.sh create "$LAB"
mkdir -p "$LAB/tmux" "$LAB/user" "$LAB/projects/demo"
cleanup() { TMUX_TMPDIR="$LAB/tmux" tmux -L fm-lab kill-server 2>/dev/null || true; chmod -R u+w "$LAB"; rm -rf "$LAB"; }
trap cleanup EXIT
export FM_HOME="$LAB" HOME="$LAB/user" CLAUDE_CONFIG_DIR="$LAB/user" TREEHOUSE_ROOT="$LAB/pool" TMUX_TMPDIR="$LAB/tmux"
unset FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE DISABLE_AUTOUPDATER
if [ -n "${EXPLICIT:-}" ]; then export DISABLE_AUTOUPDATER="$EXPLICIT"; fi
export FM_SPAWN_NO_GUARD=1
printf 'claude\n' > "$LAB/config/crew-harness"
git -C "$LAB/projects/demo" init -q -b main
printf 'disposable launch fixture\n' > "$LAB/projects/demo/README.md"
git -C "$LAB/projects/demo" add README.md
git -C "$LAB/projects/demo" -c user.name=Lab -c user.email=lab@example.invalid commit -qm fixture
tmux -L fm-lab new-session -d -s primary -x 120 -y 40 -c "$ROOT"
export TMUX=$(tmux -L fm-lab display-message -p '#{socket_path}'),0,0
mkdir -p "$LAB/data/AU-live"
printf '# Task\n## Captain\x27s intent\nObserve launch environment only.\n## Firstmate spec\nDo no work.\n' > "$LAB/data/AU-live/brief.md"
if [ "${FILTER:-0}" = 1 ]; then : > "$LAB/config/launch-env-allowlist"; fi
if [ "${KIND:-scout}" = ship ]; then mode=(--mode no-mistakes --yolo off); else mode=(--scout); fi
bin/fm-spawn.sh AU-live "$LAB/projects/demo" "${mode[@]}" --harness "${LAUNCH_CMD:-claude}" --backend tmux > "$E/${NAME:-scout}-spawn.txt" 2>&1
sleep 5
if [ "${RELAUNCH:-0}" = 1 ]; then
 bin/fm-spawn.sh AU-live --relaunch --harness "${LAUNCH_CMD:-claude}" >> "$E/${NAME:-scout}-spawn.txt" 2>&1
 sleep 5
fi
tmux -L fm-lab list-panes -a -F '#{pane_id} #{pane_pid} #{pane_current_command}' > "$E/${NAME:-scout}-panes.txt"
tmux -L fm-lab capture-pane -p -t primary:fm-AU-live > "$E/${NAME:-scout}-claude-pane.txt" || true
if [ -n "${LAUNCH_CMD:-}" ]; then
  cat "$E/${NAME:-scout}-claude-pane.txt"
  exit 0
fi
python3 - "$LAB" <<'PY'
import subprocess,sys,json
lab=sys.argv[1]
rows=subprocess.check_output(['ps','-axo','pid=,ppid=,comm='],text=True).splitlines()
found=[]
for row in rows:
    parts=row.strip().split(None,2)
    if len(parts)!=3 or 'claude' not in parts[2]: continue
    s=subprocess.check_output(['ps','eww','-p',parts[0]],text=True)
    if lab not in s: continue
    vals={}
    for key in ['DISABLE_AUTOUPDATER','CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION','FM_HOME']:
        import re
        m=re.search(r'(?:^| )'+key+r'=([^ ]*)',s)
        vals[key]=m.group(1) if m else None
    found.append(dict(pid=parts[0],command=parts[2],environment=vals))
print(json.dumps(found,indent=2))
assert found and all(x['environment']['DISABLE_AUTOUPDATER']=='1' for x in found)
PY
