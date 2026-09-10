set -u
. "$1/tests/lib.sh"
RUNNER=$2
test_list_scheduled_proven_isolated_uses_serial_weights() {
  local tmp
  tmp=$(fm_test_tmproot fm-test-run-proven-schedule)
  "$RUNNER" --list --proven-isolated | LC_ALL=C sort >"$tmp/expected"
  "$RUNNER" --list-scheduled --proven-isolated >"$tmp/actual" \
    || fail "--list-scheduled --proven-isolated failed"
  cmp -s "$tmp/expected" "$tmp/actual" \
    || fail "proven-isolated scheduling must break serial-default ties by path"
  pass "proven-isolated scheduling ignores parallel hints"
}

test_list_scheduled_non_lane_selections_use_serial_weights() {
  local tmp repo script selection
  local -a scripts=(
    tests/fm-operational-input.test.sh
    tests/fm-lint.test.sh
    tests/fm-muse-harness.test.sh
    tests/fm-captain-hold-lifecycle.test.sh
    tests/fm-kimi-harness.test.sh
    tests/fm-brief.test.sh
  )
  tmp=$(fm_test_tmproot fm-test-run-non-lane-schedule)
  repo="$tmp/repo"
  mkdir -p "$repo/bin" "$repo/tests"
  cp "$RUNNER" "$repo/bin/fm-test-run.sh"
  for script in "${scripts[@]}"; do
    printf '#!/usr/bin/env bash\nexit 0\n' >"$repo/$script"
    chmod +x "$repo/$script"
  done
  git -C "$repo" init -q
  git -C "$repo" add .
  git -C "$repo" -c user.name=test -c user.email=test@example.invalid commit -qm baseline
  for script in "${scripts[@]}"; do
    printf '\n' >>"$repo/$script"
  done
  printf '%s\n' \
    tests/fm-muse-harness.test.sh \
    tests/fm-brief.test.sh \
    tests/fm-captain-hold-lifecycle.test.sh \
    tests/fm-lint.test.sh \
    tests/fm-kimi-harness.test.sh \
    tests/fm-operational-input.test.sh >"$tmp/expected"
  for selection in family all changed scripts; do
    case "$selection" in
      family) set -- --family pure-contract-unit ;;
      all) set -- --all ;;
      changed) set -- --changed --base HEAD ;;
      scripts) set -- "${scripts[@]}" ;;
    esac
    "$repo/bin/fm-test-run.sh" --list-scheduled "$@" >"$tmp/actual" \
      || fail "--list-scheduled $selection failed"
    cmp -s "$tmp/expected" "$tmp/actual" \
      || fail "$selection scheduling must use serial hints and path-ordered default ties"
  done
  pass "family, all, changed, and script selections ignore parallel hints"
}


"$3"
