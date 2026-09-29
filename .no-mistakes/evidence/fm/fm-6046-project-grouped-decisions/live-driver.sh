#!/bin/bash
set -euo pipefail
export FM_HOME="$PWD/.test-live/home"
unset FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE FM_FOCUS_NOW_EPOCH
bin/fm-lab-home.sh create "$FM_HOME"
cat > "$FM_HOME/data/backlog.md" <<'EOF'
## In flight

## Queued
- [ ] alpha-one - Alpha route (repo: alpha) (kind: captain) (hold: choose) (hold-kind: captain)
- [ ] beta-one - Beta release (repo: beta) (kind: captain) (hold: choose) (hold-kind: captain)
- [ ] alpha-two - Alpha backup (repo: alpha) (kind: captain) (hold: choose) (hold-kind: captain)
- [ ] unknown - Unassigned decision (kind: captain) (hold: choose) (hold-kind: captain)

## Done
EOF
f() { printf '\n$ fm-focus %s\n' "$*"; bin/fm-focus.sh "$@"; }
f status
f route --task beta-one --class completion --summary 'Beta completed'
f set alpha gamma
for cls in failure security credential blocking; do f route --task beta-one --class "$cls" --summary "Beta $cls"; done
f route --task unknown --class decision --summary Unknown
f route --task alpha-one --class decision --summary Alpha
f route --task gamma-one --project gamma --class completion --summary Gamma
f route --task beta-one --class decision --summary 'Beta release needs your decision'
f route --task delta-one --project delta --class review-ready --summary 'Delta review ready'
f route --task beta-one --class completion --summary 'Beta audit completed'
f status --json
bin/fm-bearings-snapshot.sh --json > "$EVIDENCE/live-snapshot.json"
cat "$EVIDENCE/live-snapshot.json"
f held
f clear
f status --json
bin/fm-wake-drain.sh > "$EVIDENCE/live-drain.txt"
cat "$EVIDENCE/live-drain.txt"
f delivered --through 3
f held
until=$(date -u -v+3S +%Y-%m-%dT%H:%M:%SZ)
f set alpha --until "$until"
f route --task beta-one --class completion --summary 'Beta timed completion'
sleep 4
f expire
f drain-section
f expire
f delivered --through 4
printf 'corrupt\n' > "$FM_HOME/state/focus-window"
f route --task beta-one --class decision --summary 'Beta fallback'
f clear
