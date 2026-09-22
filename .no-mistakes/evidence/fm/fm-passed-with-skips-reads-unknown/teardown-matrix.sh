#!/usr/bin/env bash
set -u
export PHASE_ROOT="$PWD" TMPDIR="$PWD/.test-phase/tmp" FM_HOME="$PWD/.test-phase/home"
. "$PHASE_ROOT/.test-phase/fm-teardown-defs.sh"
printf '%s\n' 'Behavioral simulation: real fm-teardown CLI and isolated git repos; fake no-mistakes, treehouse, tmux and forge. NOT LIVE. No real pipeline is aborted.'
probe() {
  local name=$1 token=$2 identity=$3 expected=$4 version=${5:-target} d head rc
  d=$(make_case "$name")
  write_meta "$d" no-mistakes ship
  land_shippable_commit "$d"
  head=$(git -C "$d/wt" rev-parse HEAD)
  cat > "$d/fakebin/treehouse" <<EOF
#!/usr/bin/env bash
printf '%s\\n' 'worktree-return-called' >> '$d/removal-log'
EOF
  chmod +x "$d/fakebin/treehouse"
  TEARDOWN="$ROOT/bin/fm-teardown.sh"
  [ "$version" != base ] || TEARDOWN="$ROOT/.test-phase/base/bin/fm-teardown.sh"
  rc=0
  FM_FAKE_AXI_STATUS="$(parked_axi_status_toon fm/task-x1 "$head")" \
  FM_FAKE_NM_ABORT_LOG="$d/nm-abort.log" \
  FM_FAKE_AXI_STATUS_AFTER_ABORT="$(printf 'run:\n  id: "%s"\n  outcome: %s\n' "$identity" "$token")" \
    run_teardown "$d" > "$d/stdout" 2> "$d/stderr" || rc=$?
  printf '\nSCENARIO %s (%s)\nPost-abort input outcome: %s; run id: %s\nExit: %s\n' "$name" "$version" "$token" "$identity" "$rc"
  cat "$d/stdout" "$d/stderr"
  if [ -e "$d/state/task-x1.meta" ]; then printf 'task metadata: retained\n'; else printf 'task metadata: removed\n'; fi
  if [ -e "$d/removal-log" ]; then printf 'worktree release: called\n'; else printf 'worktree release: not called\n'; fi
  expect_code "$expected" "$rc" "$name exit"
  if [ "$expected" = 1 ]; then
    assert_present "$d/state/task-x1.meta" "$name must retain metadata"
    assert_absent "$d/removal-log" "$name must not release worktree"
  else
    assert_absent "$d/state/task-x1.meta" "$name removes metadata after terminal proof"
    assert_present "$d/removal-log" "$name releases completed worktree"
  fi
}
probe skips-base passed-with-skips 01RUN 1 base
probe skips-terminal passed-with-skips 01RUN 0
probe skips-wrong-run passed-with-skips 01OTHER 1
probe unknown-outcome passed-with-skip 01RUN 1
probe override-terminal passed-with-override 01RUN 0
