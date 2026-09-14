#!/usr/bin/env bash
set -eu
. "$PWD/tests/wake-helpers.sh"
dir=$(fm_test_tmproot fm-liveness-evidence)
sleep 30 &
pid=$!
trap 'kill -KILL "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fm_test_cleanup' EXIT
rc=0
is_live_non_zombie "$pid" || rc=$?
printf 'real running pid=%s observed_state=%s (0=live)\n' "$pid" "$rc"
[ "$rc" -eq 0 ]
# A missing process reader is a real process-environment failure, not a ps stub.
mkdir "$dir/path-without-ps"
ln -s /bin/sleep "$dir/path-without-ps/sleep"
rc=0
PATH="$dir/path-without-ps" is_live_non_zombie "$pid" || rc=$?
printf 'present pid=%s, ps unavailable: observed_state=%s (2=unknown)\n' "$pid" "$rc"
[ "$rc" -eq 2 ]
rc=0
started=$SECONDS
PATH="$dir/path-without-ps" wait_for_exit "$pid" 3 || rc=$?
printf 'wait_for_exit with ps unavailable: exit=%s elapsed=%ss (124=bounded refusal)\n' "$rc" "$((SECONDS-started))"
[ "$rc" -eq 124 ]
kill -KILL "$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true
rc=0
PATH="$dir/path-without-ps" is_live_non_zombie "$pid" || rc=$?
printf 'reaped pid=%s, ps unavailable: observed_state=%s (1=gone)\n' "$pid" "$rc"
[ "$rc" -eq 1 ]
