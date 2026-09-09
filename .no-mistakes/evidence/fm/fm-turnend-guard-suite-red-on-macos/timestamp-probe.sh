#!/usr/bin/env bash
set -eu
. "${1:-tests/lib.sh}"
PROBE_ROOT=$(fm_test_tmproot fm-epoch-probe)
printf 'os=%s bash=%s date=%s touch=%s caller_TZ=%s\n' "$(uname -s)" "$BASH_VERSION" "$(command -v date)" "$(command -v touch)" "$TZ"
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"; }
now=$(date +%s)
for epoch in 1761438600 1761442200 "$((now - 400))" "$((now - 700))"; do
  fm_touch_epoch "$epoch" "$PROBE_ROOT/beacon" "$PROBE_ROOT/beacon with spaces"
  for path in "$PROBE_ROOT/beacon" "$PROBE_ROOT/beacon with spaces"; do
    actual=$(mtime "$path")
    printf 'requested_epoch=%s observed_mtime=%s file=%s caller_TZ=%s\n' "$epoch" "$actual" "$(basename "$path")" "$TZ"
    [ "$actual" = "$epoch" ] || fail 'epoch changed during round-trip'
    [ "$TZ" = Europe/Paris ] || fail 'caller timezone changed'
  done
done
if output=$(fm_touch_epoch definitely-invalid "$PROBE_ROOT/invalid" 2>&1); then
  fail 'invalid epoch unexpectedly succeeded'
else
  printf 'invalid_epoch exit=%s output=%s\n' "$?" "$output"
fi
[ ! -e "$PROBE_ROOT/invalid" ] || fail 'invalid conversion created a file'
if output=$(fm_touch_epoch 1761438600 "$PROBE_ROOT/missing-parent/beacon" 2>&1); then
  fail 'missing parent unexpectedly succeeded'
else
  printf 'missing_parent exit=%s output=%s\n' "$?" "$output"
fi
touch -t 202001010000 "$PROBE_ROOT/stale-backlog.lock"
actual=$(mtime "$PROBE_ROOT/stale-backlog.lock")
printf 'stale_backlog_lock stamp=202001010000 observed_mtime=%s older_than_now=%s\n' "$actual" "$((now-actual))"
[ "$actual" -lt "$((now-600))" ] || fail 'backlog lock was not aged'
