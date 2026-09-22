# Test-phase harness: execute selected existing behavioral cases and expose the
# actual current-state output. All no-mistakes and pane inputs remain fakes.
if [ "${PHASE_BASE:-0}" = 1 ]; then
  CREW_STATE="$ROOT/.test-phase-tmp/base-bin/fm-crew-state.sh"
fi
run_crew_state() {
  local out
  out=$(PATH="$1/fakebin:$PATH" FM_STATE_OVERRIDE="$1/state" "$CREW_STATE" "$2")
  printf '%s\n' "$out" >&2
  printf '%s\n' "$out"
}

phase_worker_inventory_guards() {
  local mode d primary out before after
  for mode in missing mismatched truncated ambiguous competing; do
    make_capped_runs_case "phase-worker-$mode" running cancelled
    d="$TMP_ROOT/phase-worker-$mode"
    primary="$d/registered-primary"
    mkdir -p "$primary"
    python3 - "$NM_HOME/state.sqlite" "$primary" "$d/wt" "$mode" <<'PYGUARD'
import sqlite3, sys
dbpath, primary, worker, mode = sys.argv[1:]
with sqlite3.connect(dbpath) as db:
    db.execute("UPDATE repos SET working_path=? WHERE id='repo'", (primary,))
    if mode == 'mismatched':
        db.execute("DELETE FROM runs WHERE id='01NEW'")
    elif mode == 'ambiguous':
        db.execute("INSERT INTO repos VALUES ('worker-repo', ?)", (worker,))
    elif mode == 'competing':
        db.execute("UPDATE runs SET status='running' WHERE id='01OLD'")
PYGUARD
    FM_FAKE_AXI_HOME="$(printf 'repo: %s\n' "$primary"; printf '%s\n' "$FM_FAKE_AXI_HOME" | tail -n +2)"
    case "$mode" in
      missing) rm "$NM_HOME/state.sqlite" ;;
      truncated) FM_FAKE_AXI_HOME=$(printf '%s\n' "$FM_FAKE_AXI_HOME" | sed '$d') ;;
    esac
    printf '\nWORKER INVENTORY GUARD %s\n' "$mode"
    before=missing
    [ ! -e "$NM_HOME/state.sqlite" ] || before=$(git hash-object "$NM_HOME/state.sqlite")
    out=$(run_crew_state "$d" competing)
    assert_contains "$out" 'state: unknown' "$mode must not yield a confident state"
    assert_contains "$out" '01NEW' "$mode retains the visible candidate id"
    if [ "$mode" = competing ]; then
      assert_contains "$out" '01OLD' 'hidden competing run remains visible'
    fi
    after=missing
    [ ! -e "$NM_HOME/state.sqlite" ] || after=$(git hash-object "$NM_HOME/state.sqlite")
    [ "$before" = "$after" ] || fail 'state read modified the inventory'
    pass "worker-copy $mode inventory remains unknown without modifying the database"
  done
}


phase_primary_worker_parity() {
  local mode d worker_out primary_out primary
  for mode in absent completed; do
    case "$mode" in
      absent) test_capped_overview_worker_copy_repo_line_reports_absent ;;
      completed) test_capped_overview_worker_copy_repo_line_reports_completed_outside_window ;;
    esac
    d="$TMP_ROOT/capped-worker-copy-$mode"
    primary="$d/primary-clone"
    git clone -q --local --no-hardlinks "$d/wt" "$primary"
    worker_out=$(run_crew_state "$d" worker)
    fm_write_meta "$d/state/worker.meta" "window=fm:fm-worker" "worktree=$primary" "kind=ship" "harness=claude"
    primary_out=$(run_crew_state "$d" worker)
    printf '\nPARITY %s\nworker: %s\nprimary: %s\n' "$mode" "$worker_out" "$primary_out"
    [ "$worker_out" = "$primary_out" ] || fail 'primary and worker current-state verdicts differ'
    pass "$mode primary and worker copies report the same current state"
  done
}

for selected_test in "$@"; do
  printf '\nCASE %s (baseline=%s)\n' "$selected_test" "${PHASE_BASE:-0}"
  "$selected_test"
done
