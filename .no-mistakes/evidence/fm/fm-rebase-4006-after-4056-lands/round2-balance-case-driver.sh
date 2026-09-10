set -u
. /Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M25C6PVFERGFF8VCGKNJPMP3/tests/lib.sh
RUNNER=$1
shift
shard_balance_artifact() {
  local dir=$1 lane=$2 wall=$3 out entries pair
  shift 3
  out="$dir/fm-test-timing-$lane.json"
  entries=""
  for pair in "$@"; do
    [ -z "$entries" ] || entries="$entries,"
    entries="$entries{\"path\": \"${pair%%:*}\", \"family\": \"afk\", \"duration_ms\": ${pair##*:}, \"exit\": 0, \"gate_skip\": false}"
  done
  cat >"$out" <<JSON
{
  "run_id": "$lane",
  "selection": "lane=$lane",
  "started_at": "2026-09-10T00:00:00Z",
  "finished_at": "2026-09-10T00:30:00Z",
  "summary": {"total": $#, "failed": 0, "skipped_gate": 0, "duration_ms": $wall},
  "scripts": [$entries]
}
JSON
  printf '%s\n' "$out"
}

# The job cap the guard scores against, read back from its own output rather
# than from the runner's source.
shard_balance_bound_ms() {
  local tmp a out bound
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/fm-test-run-balance-bound.XXXXXX")
  a=$(shard_balance_artifact "$tmp" portable-serial-1of1 1000 "tests/a.test.sh:1000")
  out=$("$RUNNER" --check-shard-balance "$a") || {
    rm -rf "$tmp"
    return 1
  }
  bound=$(printf '%s\n' "$out" | sed -n 's/.*bound=\([0-9]*\)min.*/\1/p')
  rm -rf "$tmp"
  [ -n "$bound" ] || return 1
  printf '%s\n' $((bound * 60000))
}

test_shard_balance_passes_and_reports_bound() {
  local tmp bound a b out
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/fm-test-run-balance-ok.XXXXXX")
  bound=$(shard_balance_bound_ms) || fail "could not read the guard's job cap"
  a=$(shard_balance_artifact "$tmp" portable-serial-1of2 $((bound / 4)) "tests/a.test.sh:$((bound / 4))")
  b=$(shard_balance_artifact "$tmp" portable-serial-2of2 $((bound / 5)) "tests/b.test.sh:$((bound / 5))")
  out=$("$RUNNER" --check-shard-balance "$a" "$b") \
    || fail "balanced shards must pass the balance guard"
  assert_contains "$out" "FM_TEST_SHARD_BALANCE ok shards=2" "balance guard reports both shards"
  assert_contains "$out" "bound=" "balance guard names the cap it scored against"
  rm -rf "$tmp"
  pass "shard balance: shards well inside the cap pass and report the bound"
}

test_shard_balance_pins_the_72_percent_threshold() {
  # Declare the expected share here so changing the runner's threshold cannot
  # move the test's expectation with it.
  local expected_percent=72
  local tmp bound threshold below above a out rc
  tmp=$(fm_test_tmproot fm-test-run-balance-threshold)
  bound=$(shard_balance_bound_ms) || fail "could not read the guard's job cap"
  # Whole-minute caps make this percentage exact in milliseconds.
  threshold=$((bound * expected_percent / 100))
  below=$((threshold - 1))
  above=$((threshold + 1))
  a=$(shard_balance_artifact "$tmp" portable-serial-1of1 "$below" "tests/a.test.sh:$below")
  out=$("$RUNNER" --check-shard-balance "$a" 2>&1) \
    || fail "a shard just below ${expected_percent}% of the job cap must pass: $out"
  a=$(shard_balance_artifact "$tmp" portable-serial-1of1 "$above" "tests/a.test.sh:$above")
  rc=0
  out=$("$RUNNER" --check-shard-balance "$a" 2>&1) || rc=$?
  [ "$rc" -eq 1 ] \
    || fail "a shard just above ${expected_percent}% of the job cap must fail (exit $rc): $out"
  rm -rf "$tmp"
  pass "shard balance: the threshold is pinned at ${expected_percent}% of the job cap"
}

test_shard_balance_goes_red_on_an_imbalanced_shard() {
  # The guard is only worth shipping if it can fail. One shard is parked just
  # under the cap while its sibling idles; the guard must refuse and say so.
  local tmp bound a b out rc
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/fm-test-run-balance-red.XXXXXX")
  bound=$(shard_balance_bound_ms) || fail "could not read the guard's job cap"
  a=$(shard_balance_artifact "$tmp" portable-serial-1of2 $((bound * 99 / 100)) "tests/slow.test.sh:$((bound * 99 / 100))")
  b=$(shard_balance_artifact "$tmp" portable-serial-2of2 $((bound / 10)) "tests/fast.test.sh:$((bound / 10))")
  rc=0
  out=$("$RUNNER" --check-shard-balance "$a" "$b" 2>&1) || rc=$?
  [ "$rc" -ne 0 ] || fail "a shard at 99% of the job cap must fail the balance guard"
  assert_contains "$out" "shard balance guard failed" "balance guard states the refusal"
  assert_contains "$out" "portable-serial-1of2" "balance guard names the offending shard"
  assert_contains "$out" "job cap" "balance guard names the cap it scored against"
  rm -rf "$tmp"
  pass "shard balance: a shard near its job cap turns the guard red"
}

test_shard_balance_goes_red_on_a_stale_hint_table() {
  # The failure the guard exists for: the hints still parse and still cover the
  # lane, but they no longer describe reality. The refusal must name the scripts
  # to re-measure, not merely say a shard was slow.
  local tmp bound a out rc
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/fm-test-run-balance-stale.XXXXXX")
  bound=$(shard_balance_bound_ms) || fail "could not read the guard's job cap"
  # fm-watch-triage.test.sh is hinted; here it runs far over that hint and
  # carries the shard past the cap share on its own.
  a=$(shard_balance_artifact "$tmp" portable-serial-1of1 $((bound * 95 / 100)) \
    "tests/fm-watch-triage.test.sh:$((bound * 90 / 100))" \
    "tests/fm-teardown.test.sh:$((bound * 5 / 100))")
  rc=0
  out=$("$RUNNER" --check-shard-balance "$a" 2>&1) || rc=$?
  [ "$rc" -ne 0 ] || fail "a shard whose scripts ran far over their hints must fail the guard"
  assert_contains "$out" "re-measure the scripts furthest over their hints" \
    "balance guard says what to re-measure"
  assert_contains "$out" "tests/fm-watch-triage.test.sh" \
    "balance guard names the drifted script"
  rm -rf "$tmp"
  pass "shard balance: a stale hint table turns the guard red and names what drifted"
}

test_shard_balance_measures_the_recorded_wall_time() {
  # The shard's own recorded wall clock decides, not the sum of its scripts: a
  # lane that spends time between scripts must not score as if it did not.
  local tmp bound a out rc
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/fm-test-run-balance-wall.XXXXXX")
  bound=$(shard_balance_bound_ms) || fail "could not read the guard's job cap"
  a=$(shard_balance_artifact "$tmp" portable-serial-1of1 $((bound * 99 / 100)) "tests/a.test.sh:1000")
  rc=0
  out=$("$RUNNER" --check-shard-balance "$a" 2>&1) || rc=$?
  [ "$rc" -ne 0 ] || fail "the guard must score the recorded wall time, not the script sum"
  assert_contains "$out" "shard balance guard failed" "wall-time shard is refused"
  rm -rf "$tmp"
  pass "shard balance: the shard's recorded wall time is what is scored"
}

test_shard_balance_reports_missing_artifacts() {
  # A cancelled shard uploads no artifact, so the guard must say how much of the
  # partition it could actually read instead of implying it checked all of it.
  local tmp bound a out
  tmp=$(mktemp -d "${TMPDIR:-/tmp}/fm-test-run-balance-partial.XXXXXX")
  bound=$(shard_balance_bound_ms) || fail "could not read the guard's job cap"
  a=$(shard_balance_artifact "$tmp" portable-serial-1of5 $((bound / 4)) "tests/a.test.sh:$((bound / 4))")
  out=$("$RUNNER" --check-shard-balance "$a") \
    || fail "one readable shard under the cap must still pass"
  assert_contains "$out" "FM_TEST_SHARD_BALANCE partial 1 of 5" \
    "balance guard reports how many shards it could read"
  rm -rf "$tmp"
  pass "shard balance: missing shard artifacts are reported, not assumed green"
}

for test_name in "$@"; do "$test_name"; done
