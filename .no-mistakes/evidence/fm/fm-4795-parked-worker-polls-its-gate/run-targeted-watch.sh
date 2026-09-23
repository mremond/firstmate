#!/usr/bin/env bash
set -eu
selectors=(
 test_busy_turn_at_unchanged_parked_gate_wakes_as_looping
 test_parked_loop_run_step_change_keeps_working
 test_parked_loop_worktree_write_keeps_working
 test_parked_loop_completed_turn_ends_episode
 test_parked_loop_steer_still_resumes_worker
 test_parked_loop_inner_notifications_keep_episode
 test_parked_loop_busy_revisions_keep_episode
 test_parked_loop_rearm_ends_episode
 test_parked_loop_default_and_zero_use_900_seconds
 test_parked_loop_recordless_busy_wakes
 test_parked_loop_away_mode_wakes
)
for selector in "${selectors[@]}"; do
  printf '\nCOMMAND: FM_TEST_ONLY=%s bash tests/fm-watch-triage.test.sh\n' "$selector"
  FM_TEST_ONLY="$selector" bash tests/fm-watch-triage.test.sh
done
