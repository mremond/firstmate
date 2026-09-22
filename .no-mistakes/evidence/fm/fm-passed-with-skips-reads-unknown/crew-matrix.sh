#!/usr/bin/env bash
set -eu
export PHASE_ROOT="$PWD" TMPDIR="$PWD/.test-phase/tmp" FM_HOME="$PWD/.test-phase/home"
. "$PHASE_ROOT/.test-phase/fm-crew-state-defs.sh"
printf '%s\n' 'Behavioral simulation: real fm-crew-state CLI, isolated git repos and state, fake no-mistakes/forge/backend responses. NOT LIVE.'
probe() {
  local name=$1 token=$2 prmode=$3 expected=$4 d out
  reset_fakes
  d=$(new_case "$name")
  make_repo_on_branch "$d/wt" "fm/$name"
  make_fakebin "$d" >/dev/null
  fm_write_meta "$d/state/$name.meta" "window=fm:fm-$name" "worktree=$d/wt" 'kind=ship'
  FM_FAKE_AXI_STATUS="$(run_passed_with_skips "fm/$name")"
  FM_FAKE_AXI_STATUS="${FM_FAKE_AXI_STATUS/passed-with-skips/$token}"
  case "$prmode" in
    open) FM_FAKE_PR_STATE=OPEN; FM_FAKE_PR_MERGED=false ;;
    unavailable) FM_FAKE_PR_READ_FAIL=1 ;;
    missing) FM_FAKE_AXI_STATUS=$(printf '%s\n' "$FM_FAKE_AXI_STATUS" | sed '/^  pr:/d') ;;
  esac
  printf '\nSCENARIO %s\nInput outcome: %s; PR: %s\n' "$name" "$token" "$prmode"
  out=$(run_crew_state "$d" "$name")
  printf 'TARGET: %s\n' "$out"
  assert_contains "$out" "state: $expected" "$name state"
  if [ "$token" = passed-with-skips ]; then
    assert_contains "$out" 'publication/CI verification skipped' "$name skip visibility"
  fi
  if [ "$prmode" = open ]; then
    assert_not_contains "$out" 'PR merged' "$name cannot claim merged"
    assert_contains "$out" 'PR open' "$name awaiting merge"
  fi
  if [ "$prmode" = unavailable ] || [ "$prmode" = missing ]; then
    assert_contains "$out" 'PR state unknown' "$name retains PR uncertainty"
  fi
  if [ "$name" = skips-open ]; then
    out=$(PATH="$d/fakebin:$PATH" FM_STATE_OVERRIDE="$d/state" "$PHASE_ROOT/.test-phase/base/bin/fm-crew-state.sh" "$name")
    printf 'BASE: %s\n' "$out"
    assert_contains "$out" 'state: unknown' 'base must reproduce reported failure'
  fi
}
probe skips-open passed-with-skips open done
probe skips-merged passed-with-skips merged done
probe skips-no-pr passed-with-skips missing done
probe skips-unreadable-pr passed-with-skips unavailable done
probe unknown-token passed-with-skip merged unknown
probe cancelled-unchanged cancelled merged failed
probe failed-unchanged failed merged failed
probe passed-unchanged passed merged done
probe override-preserved passed-with-override open done
