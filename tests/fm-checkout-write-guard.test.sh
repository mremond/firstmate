#!/usr/bin/env bash
# Contract tests for bin/fm-checkout-write-guard.sh and for the enforcement
# bin/fm-test-run.sh builds on it.
#
# The point of these tests is that the guarantee CAN FAIL. A check that only
# ever agrees with itself is green forever and worth nothing, so every case
# below is a mutation pair: the same fixture with a write and without it, and
# the two verdicts must differ. Nothing here asserts the guard's source; each
# case drives the guard and the runner through their command line.
#
# Every fixture hands its payload to `sh -c '...' _ <root>`, so the single quotes
# are deliberate: $1 belongs to that shell, not to this one.
# shellcheck disable=SC2016
set -u

# shellcheck source=tests/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

GUARD="$ROOT/bin/fm-checkout-write-guard.sh"
RUNNER="$ROOT/bin/fm-test-run.sh"

assert_present "$GUARD" "bin/fm-checkout-write-guard.sh is missing"
[ -x "$GUARD" ] || fail "bin/fm-checkout-write-guard.sh must be executable"

TMP_ROOT=$(fm_test_tmproot fm-checkout-write-guard)

# A stand-in checkout: a real git repository with one tracked file and a
# gitignored directory, so the fixtures can exercise tracked, untracked and
# ignored paths without ever touching the repository this suite runs from.
make_fake_checkout() {  # <name> -> echoes its path
  local root="$TMP_ROOT/$1"
  fm_git_init_commit "$root"
  printf 'state/\n' > "$root/.gitignore"
  mkdir -p "$root/bin"
  printf 'tracked\n' > "$root/bin/thing.sh"
  git -C "$root" add .gitignore bin/thing.sh
  git -C "$root" -c user.name='Firstmate Tests' -c user.email='tests@example.invalid' \
    commit -qm fixture
  printf '%s\n' "$root"
}

# Run the guard around <command...> and echo "<exit>|<combined output>".
guarded() {  # <root> <label> -- <command...>
  local root=$1 label=$2 out rc
  shift 2
  [ "${1:-}" = -- ] && shift
  out=$("$GUARD" --root "$root" --label "$label" run -- "$@" 2>&1) && rc=0 || rc=$?
  printf '%s|%s' "$rc" "$out"
}

# --- the mutation pair: a write is refused, the same script without it is not -

test_write_into_the_checkout_is_refused_and_the_absence_of_it_is_not() {
  local root red green
  root=$(make_fake_checkout mutation)

  # Same script, one line apart. WITH the write:
  red=$(guarded "$root" writer -- sh -c 'mkdir -p "$1/state"' _ "$root")
  [ "${red%%|*}" -ne 0 ] || fail "a script that created a path in the checkout was NOT refused"
  assert_contains "${red#*|}" "FM_CHECKOUT_WRITE writer created ./state" \
    "the refusal did not name the created path"
  assert_contains "${red#*|}" "$root" "the refusal did not name the checkout"

  # WITHOUT the write, everything else identical:
  rm -rf "$root/state"
  green=$(guarded "$root" writer -- sh -c 'true')
  [ "${green%%|*}" -eq 0 ] \
    || fail "a script that wrote nothing was refused: ${green#*|}"
  assert_not_contains "${green#*|}" "FM_CHECKOUT_WRITE " \
    "a clean script still produced a violation marker"

  pass "the guard refuses a script that writes into the checkout and passes the same script without the write"
}

# --- the maintainer's-machine case ------------------------------------------
#
# The original defect was invisible on a developer's copy precisely because the
# gitignored directory was already there. A write INSIDE an existing ignored
# directory must still be caught, or the guard reproduces the disease.

test_a_write_inside_an_existing_ignored_directory_is_still_caught() {
  local root red green
  root=$(make_fake_checkout ignored-dir)
  mkdir -p "$root/state"

  red=$(guarded "$root" ignored -- sh -c 'printf x > "$1/state/leftover"' _ "$root")
  [ "${red%%|*}" -ne 0 ] || fail "a write inside an existing gitignored directory was not caught"
  assert_contains "${red#*|}" "created ./state/leftover" \
    "the refusal did not name the file written inside the ignored directory"

  green=$(guarded "$root" ignored -- sh -c 'true')
  [ "${green%%|*}" -eq 0 ] || fail "the guard stayed red after the write was removed: ${green#*|}"

  pass "a write inside an already-present gitignored directory is caught, not hidden"
}

# --- removal and modification -----------------------------------------------

test_removing_and_modifying_paths_are_both_refused() {
  local root out
  root=$(make_fake_checkout mutate-existing)
  mkdir -p "$root/state"
  printf 'before\n' > "$root/state/keep"

  out=$(guarded "$root" remover -- sh -c 'rm -f "$1/state/keep"' _ "$root")
  [ "${out%%|*}" -ne 0 ] || fail "a script that removed a path was not refused"
  assert_contains "${out#*|}" "removed ./state/keep" "the refusal did not name the removed path"

  printf 'longer than before\n' > "$root/state/keep"
  out=$(guarded "$root" editor -- sh -c 'printf "much much longer content\n" > "$1/state/keep"' _ "$root")
  [ "${out%%|*}" -ne 0 ] || fail "a script that modified an untracked file was not refused"
  assert_contains "${out#*|}" "modified ./state/keep" "the refusal did not name the modified path"

  out=$(guarded "$root" tracked-editor -- sh -c 'printf "edited\n" > "$1/bin/thing.sh"' _ "$root")
  [ "${out%%|*}" -ne 0 ] || fail "a script that edited a TRACKED file was not refused"
  assert_contains "${out#*|}" "./bin/thing.sh" "the refusal did not name the edited tracked file"

  pass "removing a path, rewriting an untracked file, and editing a tracked file are each refused"
}

# --- what the guard deliberately ignores ------------------------------------

test_git_internals_alone_are_not_a_violation() {
  local root out
  root=$(make_fake_checkout git-internals)

  # A commit rewrites .git and nothing else. The guard prunes .git on purpose:
  # its subject is the working tree the next script will read.
  out=$(guarded "$root" committer -- \
    git -C "$root" -c user.name='Firstmate Tests' -c user.email='tests@example.invalid' \
    commit -q --allow-empty -m churn)
  [ "${out%%|*}" -eq 0 ] || fail "a change confined to .git was reported as a checkout write: ${out#*|}"

  pass "changes confined to .git are not reported; the working tree is the subject"
}

# --- the guarded command's own status is preserved --------------------------

test_the_guarded_commands_exit_status_survives() {
  local root out
  root=$(make_fake_checkout status-passthrough)
  out=$(guarded "$root" failing -- sh -c 'exit 3')
  [ "${out%%|*}" -eq 3 ] \
    || fail "the guarded command's exit status was replaced: got ${out%%|*}, want 3"
  pass "a failing command keeps its own exit status through the guard"
}

# --- tolerance is explicit, narrow, and never silent ------------------------

test_allow_globs_tolerate_only_what_they_name() {
  local root out rc
  root=$(make_fake_checkout allow-globs)

  out=$("$GUARD" --root "$root" --label allowed --allow './state' --allow './state/*' \
    run -- sh -c 'mkdir -p "$1/state"; printf x > "$1/state/f"' _ "$root" 2>&1) && rc=0 || rc=$?
  [ "$rc" -eq 0 ] || fail "an explicitly allowed path was still refused: $out"
  assert_contains "$out" "FM_CHECKOUT_WRITE_PINNED allowed created ./state" \
    "a tolerated write must still be reported, not silently dropped"

  # The same run, one path outside the allowance, is refused.
  rm -rf "$root/state"
  out=$("$GUARD" --root "$root" --label allowed --allow './state' --allow './state/*' \
    run -- sh -c 'mkdir -p "$1/state"; printf x > "$1/elsewhere"' _ "$root" 2>&1) && rc=0 || rc=$?
  [ "$rc" -ne 0 ] || fail "a path outside the allowance was tolerated: $out"
  assert_contains "$out" "FM_CHECKOUT_WRITE allowed created ./elsewhere" \
    "the refusal did not name the path outside the allowance"

  pass "an allowance tolerates only the paths it names, and says so rather than passing quietly"
}

test_the_pin_table_is_wired_to_the_guard() {
  local root row label glob out rc
  root=$(make_fake_checkout pin-table)

  # Read a row from the table rather than hard-coding one, so this case keeps
  # working as the debt shrinks - and still says something when it reaches zero.
  row=$("$GUARD" --list-pins | head -1)
  if [ -z "$row" ]; then
    out=$(guarded "$root" any-script -- sh -c 'mkdir -p "$1/state"' _ "$root")
    [ "${out%%|*}" -ne 0 ] \
      || fail "the pin table is empty, so nothing at all should be tolerated"
    pass "the pin table is empty: every script is held to the full prohibition"
    return
  fi

  label=${row%%	*}
  glob=${row#*	}
  glob=${glob%%	*}
  glob=${glob%% *}

  out=$(guarded "$root" "$label" -- sh -c 'mkdir -p "$1/state"' _ "$root")
  [ "${out%%|*}" -eq 0 ] \
    || fail "$label is pinned for $glob but its own write was refused: ${out#*|}"
  assert_contains "${out#*|}" "FM_CHECKOUT_WRITE_PINNED $label created ./state" \
    "a pinned write must be reported as recorded debt, not passed in silence"

  # The pin covers that script and nothing else: an unpinned script writing the
  # very same path is still refused.
  rm -rf "$root/state"
  out=$(guarded "$root" a-script-with-no-pin -- sh -c 'mkdir -p "$1/state"' _ "$root")
  [ "${out%%|*}" -ne 0 ] || fail "a pin leaked to a script that does not carry one"

  # And it covers that path and nothing else.
  rm -rf "$root/state"
  out=$(guarded "$root" "$label" -- sh -c 'printf x > "$1/not-pinned"' _ "$root")
  [ "${out%%|*}" -ne 0 ] || fail "$label's pin tolerated a path it does not name"

  pass "a pin tolerates one script's recorded paths and nothing else"
}

test_pipeline_owned_paths_are_exempt_and_still_reported() {
  local root out rc
  root=$(make_fake_checkout pipeline-owned)

  # The validation pipeline writes its own evidence into the checkout while it
  # is driving this very suite. Attributing that to whichever script happened to
  # be running would be wrong, so it is exempt - but never silent.
  out=$("$GUARD" --root "$root" --label pipeline \
    run -- sh -c 'mkdir -p "$1/.no-mistakes"; printf x > "$1/.no-mistakes/run"' _ "$root" 2>&1) \
    && rc=0 || rc=$?
  [ "$rc" -eq 0 ] || fail "the validation pipeline's own evidence path was refused: $out"
  assert_contains "$out" "FM_CHECKOUT_WRITE_EXEMPT pipeline created ./.no-mistakes" \
    "an exempt path must still be reported"
  assert_not_contains "$out" "FM_CHECKOUT_WRITE pipeline" \
    "an exempt path must not be counted as a violation"

  # The exemption is that path and nothing near it.
  out=$("$GUARD" --root "$root" --label pipeline \
    run -- sh -c 'printf x > "$1/.no-mistakes-elsewhere"' _ "$root" 2>&1) && rc=0 || rc=$?
  [ "$rc" -ne 0 ] || fail "the exemption leaked to a neighbouring path: $out"

  pass "the validation pipeline's own path is exempt and reported; neighbouring paths are not"
}

test_the_opt_out_announces_itself() {
  local root out rc
  root=$(make_fake_checkout opt-out)
  out=$(FM_CHECKOUT_WRITE_GUARD=off "$GUARD" --root "$root" --label off-case \
    run -- sh -c 'mkdir -p "$1/state"' _ "$root" 2>&1) && rc=0 || rc=$?
  [ "$rc" -eq 0 ] || fail "the documented opt-out did not disable the guard: $out"
  assert_contains "$out" "FM_CHECKOUT_WRITE_GUARD_OFF off-case" \
    "a disabled guard must say so; a silent pass is indistinguishable from a satisfied guarantee"
  pass "the opt-out disables the guard and announces it instead of passing silently"
}

# --- the concurrent phase ----------------------------------------------------
#
# A concurrent phase shares one checkout between workers, so it is guarded as a
# unit under the label `concurrent-phase` rather than per script. That unit must
# still carry the pins of the scripts admitted to it: without them a script
# writing exactly what its own pin records fails the phase, so the ordinary
# default run of any selection containing a pinned script goes red on debt the
# guard has already accepted. A guard that cries wolf gets switched off.

# Writes a fixture for every script pinned for exactly `./state`, each doing the
# one thing its pin records. Derived from the live pin table rather than naming
# a row, so the case follows the debt as it shrinks. Echoes how many it wrote.
write_pinned_state_fixtures() {  # <repo>
  local repo=$1 row label globs written=0
  while IFS= read -r row; do
    [ -n "$row" ] || continue
    label=${row%%	*}
    globs=${row#*	}
    globs=${globs%%	*}
    # Exactly `./state`, so the fixture is one mkdir and no glob is involved.
    [ "$globs" = "./state" ] || continue
    printf '#!/usr/bin/env bash\nmkdir -p state\necho "ok - %s"\n' "$label" >"$repo/tests/$label"
    chmod +x "$repo/tests/$label"
    written=$((written + 1))
  done < <("$GUARD" --list-pins)
  printf '%s\n' "$written"
}

test_the_concurrent_phase_carries_the_pins_of_its_scripts() {
  local repo out rc written leak

  repo=$(make_fake_checkout concurrent-phase)
  install_guarded_runner "$repo"
  written=$(write_pinned_state_fixtures "$repo")

  if [ "$written" -lt 2 ]; then
    # The debt is gone. The phase must then tolerate nothing at all, which is
    # the stricter half of the same contract.
    rm -f "$repo/tests"/*.test.sh
    printf '#!/usr/bin/env bash\nmkdir -p state\necho "ok"\n' >"$repo/tests/fm-procevent.test.sh"
    printf '#!/usr/bin/env bash\necho "ok"\n' >"$repo/tests/fm-quota-choose.test.sh"
    chmod +x "$repo/tests"/*.test.sh
    out=$(cd "$repo" && env -u FM_TASK_ID bin/fm-test-run.sh tests/fm-procevent.test.sh tests/fm-quota-choose.test.sh 2>&1) && rc=0 || rc=$?
    [ "$rc" -ne 0 ] || fail "no script is pinned for ./state, so any write there must still be refused"
    pass "no pinned ./state debt remains; a write there is refused outright"
    return
  fi

  # No --jobs: the ordinary default run, which is where the spurious refusal
  # this case pins would have appeared.
  rm -rf "$repo/state"
  out=$(cd "$repo" && env -u FM_TASK_ID bin/fm-test-run.sh tests/*.test.sh 2>&1) && rc=0 || rc=$?
  # This marker proves a concurrent phase actually formed AND consulted the
  # pins, so the case cannot pass by quietly never running concurrently.
  assert_contains "$out" "FM_CHECKOUT_WRITE_PINNED concurrent-phase created ./state" \
    "no concurrent phase reported the pinned write as recorded debt"
  [ "$rc" -eq 0 ] \
    || fail "a concurrent phase failed on writes its own scripts are pinned for: $out"

  # Mutation: one unrecorded write in the same run is still refused.
  rm -rf "$repo/state"
  leak=fm-quota-choose.test.sh
  printf '#!/usr/bin/env bash\nmkdir -p leak\necho "ok - %s"\n' "$leak" >"$repo/tests/$leak"
  chmod +x "$repo/tests/$leak"
  out=$(cd "$repo" && env -u FM_TASK_ID bin/fm-test-run.sh tests/*.test.sh 2>&1) && rc=0 || rc=$?
  [ "$rc" -ne 0 ] || fail "a path no admitted script is pinned for was tolerated: $out"
  assert_contains "$out" "created ./leak" "the unrecorded write was not reported"

  pass "a concurrent phase carries its scripts' pins and still refuses a path none of them names"
}

# --- the enforcement point --------------------------------------------------

install_guarded_runner() {  # <repo>
  mkdir -p "$1/bin" "$1/tests"
  cp "$RUNNER" "$1/bin/fm-test-run.sh"
  cp "$GUARD" "$1/bin/fm-checkout-write-guard.sh"
  chmod +x "$1/bin/fm-test-run.sh" "$1/bin/fm-checkout-write-guard.sh"
}

test_the_runner_fails_a_script_that_writes_into_the_checkout() {
  local repo out rc
  repo=$(make_fake_checkout runner-enforcement)
  install_guarded_runner "$repo"

  # A test script whose only sin is a directory it leaves behind.
  cat >"$repo/tests/fm-leaky-fixture.test.sh" <<'SH'
#!/usr/bin/env bash
mkdir -p state
echo "ok - leaky fixture asserted something"
SH
  chmod +x "$repo/tests/fm-leaky-fixture.test.sh"

  out=$(cd "$repo" && bin/fm-test-run.sh tests/fm-leaky-fixture.test.sh 2>&1) && rc=0 || rc=$?
  [ "$rc" -ne 0 ] || fail "the runner passed a script that wrote into the checkout"
  assert_contains "$out" "not ok - tests/fm-leaky-fixture.test.sh wrote into the repository checkout" \
    "the runner did not name the offending script"
  assert_contains "$out" "FM_CHECKOUT_WRITE fm-leaky-fixture.test.sh created ./state" \
    "the runner did not report the path that was written"
  assert_contains "$out" "FM_TEST_SUMMARY total=1 failed=1" \
    "the write was not counted as a failed script"

  # Mutation: remove the write, keep the assertion, and the same script is green.
  rm -rf "$repo/state"
  cat >"$repo/tests/fm-leaky-fixture.test.sh" <<'SH'
#!/usr/bin/env bash
echo "ok - leaky fixture asserted something"
SH
  chmod +x "$repo/tests/fm-leaky-fixture.test.sh"
  out=$(cd "$repo" && bin/fm-test-run.sh tests/fm-leaky-fixture.test.sh 2>&1) && rc=0 || rc=$?
  [ "$rc" -eq 0 ] || fail "the runner failed the same script once its write was removed: $out"
  assert_contains "$out" "FM_TEST_SUMMARY total=1 failed=0" "the clean script was not counted green"

  pass "the runner fails a script that writes into the checkout and passes it once the write is gone"
}

test_the_runner_refuses_to_run_without_its_guard() {
  local repo out rc
  repo=$(make_fake_checkout runner-without-guard)
  install_guarded_runner "$repo"
  printf '#!/usr/bin/env bash\necho "ok - fixture"\n' >"$repo/tests/fm-plain-fixture.test.sh"
  chmod +x "$repo/tests/fm-plain-fixture.test.sh"

  # Deleting the enforcement must be loud. This is the failure mode the guard
  # exists to survive: an automated step that removes a check nobody notices.
  rm -f "$repo/bin/fm-checkout-write-guard.sh"
  out=$(cd "$repo" && bin/fm-test-run.sh tests/fm-plain-fixture.test.sh 2>&1) && rc=0 || rc=$?
  [ "$rc" -ne 0 ] || fail "the runner ran a suite with its checkout write guard deleted"
  assert_contains "$out" "fm-checkout-write-guard.sh" \
    "the refusal did not name the missing guard"
  assert_not_contains "$out" "FM_TEST_BEGIN" \
    "the refusal must happen before any script runs"

  # Inspection executes nothing, so it stays available: a checkout missing the
  # guard must still be answerable about what it WOULD run.
  out=$(cd "$repo" && bin/fm-test-run.sh --list tests/fm-plain-fixture.test.sh 2>&1) \
    || fail "--list must remain available without the guard: $out"
  [ "$out" = "tests/fm-plain-fixture.test.sh" ] || fail "--list without the guard printed: $out"

  pass "deleting the guard stops the runner instead of silently dropping the guarantee"
}

test_write_into_the_checkout_is_refused_and_the_absence_of_it_is_not
test_a_write_inside_an_existing_ignored_directory_is_still_caught
test_removing_and_modifying_paths_are_both_refused
test_git_internals_alone_are_not_a_violation
test_the_guarded_commands_exit_status_survives
test_allow_globs_tolerate_only_what_they_name
test_the_pin_table_is_wired_to_the_guard
test_pipeline_owned_paths_are_exempt_and_still_reported
test_the_opt_out_announces_itself
test_the_runner_fails_a_script_that_writes_into_the_checkout
test_the_runner_refuses_to_run_without_its_guard
test_the_concurrent_phase_carries_the_pins_of_its_scripts

echo "# fm-checkout-write-guard.test.sh: all assertions passed"
