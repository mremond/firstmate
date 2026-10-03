#!/usr/bin/env bash
set -u
. .test-busy-lab/env.sh
. "$ROOT/bin/fm-supervise-daemon.sh"
. "$ROOT/bin/fm-task-inbox-lib.sh"
state="$FM_HOME/state"
LOG="$EVIDENCE/consumer-daemon.log"
worker="$HERDR_LAB_SESSION:$(jq -r .result.root_pane.pane_id "$ROOT/.test-busy-lab/worker.json")"
printf 'window=%s\nbackend=herdr\nharness=claude\n' "$worker" > "$state/worker.meta"
printf 'working: processing instructions\n' > "$state/worker.status"
rec=$(fm_task_inbox_write "$state" worker 'Live QA durable steering instruction; preserve until acknowledged.') || exit 1
printf 'head=%s\n' "$(git rev-parse HEAD)"
for mode in away quiet; do
  printf '%s\n' "$mode" > "$state/.afk"
  for kind in stuck write reset; do
    case "$kind" in
      stuck) detail="unread firstmate instruction: stuck-busy after 2 consecutive busy-deferred due doorbells; $rec stays unhandled and no doorbell was typed; inspect the worker" ;;
      write) detail="steering-inbox busy bookkeeping unwritable: ${rec%/*}/.busy-state cannot be written while $rec stays unhandled; inspect the inbox directory" ;;
      reset) detail="steering-inbox busy bookkeeping unwritable: ${rec%/*}/.busy-state cannot be reset after a non-busy check; inspect the inbox directory" ;;
    esac
    reason="stale: $worker ($detail)"
    fm_wake_append stale "$worker" "$reason" || exit 2
    printf 'QUEUED mode=%s reason=%s\n' "$mode" "$reason"
  cp "$state/.wake-queue" "$EVIDENCE/consumer-$mode-$kind-queue-before.tsv"
  rm -f "$state/.subsuper-escalations"
  mkdir "$state/.subsuper-escalations"
  if handle_durable_wakes "$reason" "$state"; then echo 'ERROR failed buffer unexpectedly acknowledged'; exit 3; fi
  [ -s "$state/.wake-queue" ] || exit 4
  cp "$state/.wake-queue" "$EVIDENCE/consumer-$mode-$kind-queue-retained.tsv"
  rmdir "$state/.subsuper-escalations"
  handle_durable_wakes "$reason" "$state" || exit 5
  cp "$state/.subsuper-escalations" "$EVIDENCE/consumer-$mode-$kind-buffer.txt"
  [ "$(wc -l < "$state/.subsuper-escalations" | tr -d ' ')" = 1 ] || exit 6
  [ ! -e "$state/.subsuper-stale-worker" ] || exit 7
  printf 'BUFFERED mode=%s count=1 status-offset=%s queue-retained-after-failure=yes\n' "$mode" "$(status_seen_offset "$state" worker)"
  i=0
  until escalate_flush "$state"; do
    i=$((i+1)); [ "$i" -lt 40 ] || { printf 'ERROR %s\n' "$INJECT_LAST_FAILURE"; exit 8; }
    sleep 1
  done
  printf 'DELIVERED mode=%s buffer-empty=%s\n' "$mode" "$([ ! -s "$state/.subsuper-escalations" ] && echo yes || echo no)"
  env PATH="$HERDR_ORIGINAL_PATH" "$HERDR_LAB_HELPER" run "$HERDR_LAB_SESSION" pane read "$(jq -r .result.root_pane.pane_id "$ROOT/.test-busy-lab/supervisor.json")" --source recent --lines 200 > "$EVIDENCE/consumer-$mode-$kind-supervisor.txt"
  sleep 2
  done
 done
[ -f "$rec" ] || exit 9
printf 'DONE original instruction remains unhandled\n'
