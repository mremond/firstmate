#!/usr/bin/env bash
. .test-busy-lab/env.sh
export FM_TASK_INBOX_GRACE_SECS=0
unset FM_TASK_INBOX_BUSY_MAX FM_BUSY_REGEX
. "$1"
w="$HERDR_LAB_SESSION:$(jq -r .result.root_pane.pane_id "$ROOT/.test-busy-lab/pi-worker.json")"
tail40=$(fm_backend_capture herdr "$w" 40)
if window_is_busy "$w" "$tail40"; then echo 'busy=yes'; else echo 'busy=no'; exit 21; fi
inbox_steer_check "$w" pi-worker
