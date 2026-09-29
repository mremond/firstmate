#!/bin/bash
set -euo pipefail
export FM_HOME="$PWD/l" TMUX_TMPDIR="$PWD/l/tmux"
unset FM_ROOT_OVERRIDE FM_STATE_OVERRIDE FM_DATA_OVERRIDE FM_CONFIG_OVERRIDE FM_PROJECTS_OVERRIDE FM_FOCUS_NOW_EPOCH
for mode in attended away; do
  [ "$mode" != away ] || touch "$FM_HOME/state/.afk"
  until=$(date -u -v+5S +%Y-%m-%dT%H:%M:%SZ)
  bin/fm-focus.sh set alpha --until "$until"
  bin/fm-focus.sh route --task beta-one --class completion --summary "Beta $mode expiry"
  FM_POLL=0.1 FM_CHECK_INTERVAL=999999 FM_HEARTBEAT=999999 bin/fm-watch.sh > "$EVIDENCE/watcher-$mode.txt" 2>&1 &
  watch_pid=$!
  for i in {1..150}; do
    kill -0 "$watch_pid" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "$watch_pid" 2>/dev/null; then kill "$watch_pid"; wait "$watch_pid" || true; echo 'WATCHER TIMEOUT'; exit 1; fi
  wait "$watch_pid"
  cat "$EVIDENCE/watcher-$mode.txt"
  bin/fm-focus.sh drain-section
  seq=$(bin/fm-focus.sh status --json | jq '[.held[].seq]|max')
  bin/fm-focus.sh delivered --through "$seq"
  rm -f "$FM_HOME/state/.afk"
done
