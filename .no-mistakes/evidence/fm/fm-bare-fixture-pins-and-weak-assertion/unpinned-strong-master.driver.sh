#!/usr/bin/env bash
# Full remote secondmate lifecycle over the deterministic generic SSH boundary.
set -u

# shellcheck source=tests/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
# shellcheck source=tests/remote-herdr-fixture.sh
. "$(dirname "${BASH_SOURCE[0]}")/remote-herdr-fixture.sh"

command -v jq >/dev/null 2>&1 || { echo "skip: jq not found"; exit 0; }
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
TMP_ROOT=$(fm_test_tmproot fm-remote-secondmate-e2e)
mkdir -p "$TMP_ROOT"
TMP_ROOT=$(cd "$TMP_ROOT" && pwd -P)
PARENT="$TMP_ROOT/parent"
REMOTE_ROOT="$TMP_ROOT/remote-root"
REMOTE_HOME="$TMP_ROOT/remote-home"
LOCAL_HOME="$TMP_ROOT/local-home"
FAKEBIN=$(fm_fakebin "$TMP_ROOT/fake")
SSH_COUNT="$TMP_ROOT/ssh.count"
DOCTOR_LOG="$TMP_ROOT/doctor.log"
HERDR_STATE="$TMP_ROOT/remote-herdr.state"
HERDR_LOG="$TMP_ROOT/remote-herdr.log"
TMUX_LOG="$TMP_ROOT/remote-tmux.log"
TMUX_STATE="$TMP_ROOT/remote-tmux.state"
CLAIMS="$TMP_ROOT/claims"
mkdir -p "$PARENT/data" "$PARENT/state" "$PARENT/config" "$PARENT/projects" "$REMOTE_ROOT" "$CLAIMS"
cleanup() {
  local worker_pid='' wait_attempt=0
  touch "$TMP_ROOT/provision.release" "$TMP_ROOT/seed.release" "$TMP_ROOT/handoff.release" \
    "$TMP_ROOT/inherit.release" "$TMP_ROOT/launch.release" 2>/dev/null || true
  FM_HOME="$PARENT" FM_PROCEVENT_CLAIM_ROOT="$CLAIMS" \
    "$ROOT/bin/fm-procevent.sh" sweep-home >/dev/null 2>&1 || true
  if [ -f "$TMP_ROOT/remote-jobs/worker.pid" ]; then
    worker_pid=$(cat "$TMP_ROOT/remote-jobs/worker.pid")
    kill "$worker_pid" 2>/dev/null || true
    while kill -0 "$worker_pid" 2>/dev/null && [ "$wait_attempt" -lt 100 ]; do
      wait_attempt=$((wait_attempt + 1))
      sleep 0.05
    done
  fi
  rm -rf -- "$TMP_ROOT"
}
trap cleanup EXIT

# Materialize the current branch as the remote host's tracked code root. The
# fixture is a real git repository because provisioning and guarded sync exercise
# the same clone and fast-forward path as a second Mac.
(
  cd "$ROOT" || exit
  tar --exclude=.git --exclude=.no-mistakes --exclude=data --exclude=state --exclude=config -cf - .
) | (cd "$REMOTE_ROOT" && tar -xf -)
cat > "$REMOTE_ROOT/bin/tmux" <<SH
#!/usr/bin/env bash
set -u
log='$TMUX_LOG'
state='$TMUX_STATE'
fail_send='$TMP_ROOT/tmux-send-fail'
printf '%s\n' "\$*" >> "\$log"
case "\${1:-}" in
  has-session|new-session|set-window-option) exit 0 ;;
  list-windows)
    [ -f "\$state" ] || exit 0
    name=\$(cut -d'|' -f1 "\$state")
    case "\$*" in *'#{session_name}:#{window_name}'*) printf 'firstmate:%s\n' "\$name" ;; *) printf '%s\n' "\$name" ;; esac
    exit 0
    ;;
  new-window)
    name=; cwd=
    while [ "\$#" -gt 0 ]; do
      case "\$1" in -n) shift; name=\$1 ;; -c) shift; cwd=\$1 ;; esac
      shift
    done
    printf '%s|%s\n' "\$name" "\$cwd" > "\$state"
    printf '@1\n'
    exit 0
    ;;
  display-message)
    case "\$*" in
      *'#{pane_current_path}'*) cut -d'|' -f2- "\$state" ;;
      *'#{pane_current_command}'*) printf 'codex\n' ;;
      *'#{cursor_y}'*) printf '0\n' ;;
      *'#S'*) printf 'firstmate\n' ;;
      *) printf '%%1\n' ;;
    esac
    exit 0
    ;;
  capture-pane) printf '❯\n'; exit 0 ;;
  send-keys) [ ! -f "\$fail_send" ] || exit 1; exit 0 ;;
  kill-window) rm -f -- "\$state"; exit 0 ;;
  list-panes) printf 'codex\n'; exit 0 ;;
esac
exit 0
SH
chmod +x "$REMOTE_ROOT/bin/tmux"
install_remote_herdr_fixture "$REMOTE_ROOT" "$HERDR_STATE" "$HERDR_LOG" \
  "$TMP_ROOT/herdr-send-fail" "$TMP_ROOT/herdr.sock"
git -C "$REMOTE_ROOT" init -q -b main
git -C "$REMOTE_ROOT" config user.email test@example.com
git -C "$REMOTE_ROOT" config user.name Test
git -C "$REMOTE_ROOT" add .
git -C "$REMOTE_ROOT" commit -qm 'remote fixture root'
REMOTE_ORIGIN="$TMP_ROOT/firstmate-origin.git"
git init -q --bare "$REMOTE_ORIGIN"
git -C "$REMOTE_ROOT" remote add origin "file://$REMOTE_ORIGIN"
git -C "$REMOTE_ROOT" push -q -u origin main
git --git-dir="$REMOTE_ORIGIN" symbolic-ref HEAD refs/heads/main

# One remote-backed direct-PR project. The remote home clones its origin, never
# the primary working tree.
git init -q --bare "$TMP_ROOT/alpha.git"
git -C "$PARENT/projects" init -q -b main alpha
git -C "$PARENT/projects/alpha" config user.email test@example.com
git -C "$PARENT/projects/alpha" config user.name Test
printf 'alpha\n' > "$PARENT/projects/alpha/README.md"
git -C "$PARENT/projects/alpha" add README.md
git -C "$PARENT/projects/alpha" commit -qm init
git -C "$PARENT/projects/alpha" remote add origin "file://$TMP_ROOT/alpha.git"
git -C "$PARENT/projects/alpha" push -q -u origin main
cat > "$PARENT/data/projects.md" <<EOF
- alpha [direct-PR] - alpha project (added 2026-08-02)
EOF
printf 'codex\n' > "$PARENT/config/secondmate-harness"
printf 'tmux\n' > "$PARENT/config/backend"
printf 'primary harness defaults\n' > "$PARENT/config/crew-harness"

cat > "$FAKEBIN/fake-ssh" <<'SH'
#!/usr/bin/env bash
count=$(cat "$FM_FAKE_SSH_COUNT" 2>/dev/null || echo 0)
printf '%s\n' "$((count + 1))" > "$FM_FAKE_SSH_COUNT"
while [ "$#" -gt 0 ]; do
  case "$1" in -o) shift 2 ;; --) shift; break ;; *) exit 90 ;; esac
done
host=$1
entry=$2
shift 2
[ "$host" = remote-mac ] || exit 91
[ "$entry" = fm-remote-entrypoint.sh ] || exit 92
cd "$FM_FAKE_REMOTE_CWD" || exit 93
argv_b64=$4
command_fields=$(perl -MMIME::Base64=decode_base64 -e '
  my $data=decode_base64($ARGV[0]);
  my @args=split(/\0/, $data);
  print join("\t", map { defined $_ ? $_ : "" } @args[0..2]);
' "$argv_b64")
IFS=$'\t' read -r command_name _command_action command_rel <<EOF
$command_fields
EOF
case "${FM_FAKE_SSH_MODE:-normal}:$command_name:$command_rel" in
  inherit-partial:fm-remote-inherit.sh:config/crew-harness) exit 255 ;;
  inherit-block:fm-remote-inherit.sh:data/captain-shared.md)
    cat > "$FM_FAKE_INHERIT_PAYLOAD"
    touch "$FM_FAKE_INHERIT_ENTERED"
    while [ ! -f "$FM_FAKE_INHERIT_RELEASE" ]; do sleep 0.02; done
    "$FM_FAKE_REMOTE_ENTRYPOINT" "$@" < "$FM_FAKE_INHERIT_PAYLOAD"
    exit $?
    ;;
esac
# The readiness gate is answered here rather than by the real doctor, which
# would inspect and repair the RUNNER's own account. tests/fm-remote-doctor.test.sh
# owns the doctor's real behavior against controlled account fixtures; this
# boundary owns only what the callers do with its verdict.
if [ "$command_name" = fm-remote-doctor.sh ]; then
  printf '%s %s\n' "${FM_FAKE_SSH_MODE:-normal}" "${_command_action:--}" >> "$FM_FAKE_DOCTOR_LOG"
  case "${FM_FAKE_SSH_MODE:-normal}" in
    unreachable) exit 255 ;;
    doctor-fix-unknown)
      if [ "${_command_action:-}" = --fix ]; then
        printf 'fix launchagent=applied: wrote the Aqua-scoped launch agent\n'
        exit 255
      fi
      printf 'check launchagent=fixable: no Firstmate herdr launch agent\n'
      printf 'error: this host is not ready for a remote second mate; unresolved: launchagent\n' >&2
      exit 1
      ;;
    doctor-human)
      printf 'check gui-session=human: no Aqua login session exists for uid 501\n'
      printf 'action: gui-session: log that account in once at the console\n'
      printf 'error: this host is not ready for a remote second mate; unresolved: gui-session\n' >&2
      exit 1
      ;;
    doctor-fixable)
      # Red until --fix runs on this host, green on every later read-only run.
      if [ "${_command_action:-}" = --fix ]; then
        touch "$FM_FAKE_DOCTOR_REPAIRED"
        printf 'fix launchagent=applied: wrote the Aqua-scoped launch agent\n'
        printf 'ok: remote second-mate readiness confirmed on this host\n'
        exit 0
      fi
      [ -f "$FM_FAKE_DOCTOR_REPAIRED" ] || {
        printf 'check launchagent=fixable: no Firstmate herdr launch agent\n'
        printf 'error: this host is not ready for a remote second mate; unresolved: launchagent\n' >&2
        exit 1
      }
      ;;
  esac
  printf 'check herdr=ok: /usr/bin/herdr\n'
  printf 'ok: remote second-mate readiness confirmed on this host\n'
  exit 0
fi
if [ "${FM_FAKE_SSH_MODE:-normal}" = doctor-fixable ] \
  && [ "$command_name" = fm-remote-secondmate-control.sh ] \
  && [ "$_command_action" = state ] \
  && [ ! -f "$FM_FAKE_DOCTOR_REPAIRED" ]; then
  printf 'unreadable\n'
  exit 0
fi
case "${FM_FAKE_SSH_MODE:-normal}:$command_name:$command_rel" in
  launch-nonherdr-route:fm-remote-secondmate-control.sh:*)
    [ "$_command_action" = launch ] || exit 93
    printf 'schema=fm-remote-secondmate-control.v1\n'
    printf 'backend=tmux\n'
    printf 'target=firstmate:fm-ios\n'
    printf 'harness=codex\n'
    exit 0
    ;;
  launch-default-session-route:fm-remote-secondmate-control.sh:*)
    [ "$_command_action" = launch ] || exit 93
    printf 'schema=fm-remote-secondmate-control.v1\n'
    printf 'backend=herdr\n'
    printf 'target=default:w1:p2\n'
    printf 'herdr_session=default\n'
    printf 'harness=codex\n'
    exit 0
    ;;
  provision-block-fail:fm-remote-home-provision.sh:*)
    touch "$FM_FAKE_SEED_ENTERED"
    while [ ! -f "$FM_FAKE_SEED_RELEASE" ]; do sleep 0.02; done
    exit 1
    ;;
  launch-block:fm-remote-secondmate-control.sh:*)
    [ "$_command_action" = launch ] || exit 93
    touch "$FM_FAKE_LAUNCH_ENTERED"
    while [ ! -f "$FM_FAKE_LAUNCH_RELEASE" ]; do sleep 0.02; done
    ;;
esac
case "${FM_FAKE_SSH_MODE:-normal}" in
  unreachable) exit 255 ;;
  ambiguous) "$FM_FAKE_REMOTE_ENTRYPOINT" "$@"; exit 255 ;;
  *) exec "$FM_FAKE_REMOTE_ENTRYPOINT" "$@" ;;
esac
SH
chmod +x "$FAKEBIN/fake-ssh"

publish_healthy_watcher_identity() { # <state> <home> <watch-script>
  local state=$1 home=$2 watch=$3 identity
  identity=$(FM_HOME="$PARENT" FM_STATE_OVERRIDE="$PARENT/state" /bin/bash -c \
    '. "$1"; fm_pid_identity "$2"' _ "$ROOT/bin/fm-wake-lib.sh" "$$") \
    || fail "could not derive fixture watcher identity"
  mkdir -p "$state/.watch.lock"
  printf '%s\n' "$$" > "$state/.watch.lock/pid"
  printf '%s\n' "$identity" > "$state/.watch.lock/pid-identity"
  printf '%s\n' "$home" > "$state/.watch.lock/fm-home"
  printf '%s\n' "$watch" > "$state/.watch.lock/watcher-path"
  touch "$state/.last-watcher-beat"
}

remote_env() {
  FM_HOME="$PARENT" \
  FM_ROOT_OVERRIDE="$REMOTE_ROOT" \
  FM_PROCEVENT_CLAIM_ROOT="$CLAIMS" \
  FM_SSH_BIN="$FAKEBIN/fake-ssh" \
  FM_FAKE_SSH_COUNT="$SSH_COUNT" \
  FM_FAKE_REMOTE_ENTRYPOINT="$REMOTE_ROOT/bin/fm-remote-entrypoint.sh" \
  FM_REMOTE_JOB_PLATFORM_OVERRIDE=Linux \
  FM_REMOTE_JOB_STATE_ROOT="$TMP_ROOT/remote-jobs" \
  FM_FAKE_SSH_MODE="${FM_FAKE_SSH_MODE:-normal}" \
  FM_FAKE_REMOTE_CWD="$TMP_ROOT" \
  FM_FAKE_SEED_ENTERED="$TMP_ROOT/seed.entered" \
  FM_FAKE_SEED_RELEASE="$TMP_ROOT/seed.release" \
  FM_FAKE_DOCTOR_LOG="$DOCTOR_LOG" \
  FM_FAKE_DOCTOR_REPAIRED="$TMP_ROOT/doctor.repaired" \
  FM_FAKE_INHERIT_ENTERED="$TMP_ROOT/inherit.entered" \
  FM_FAKE_INHERIT_RELEASE="$TMP_ROOT/inherit.release" \
  FM_FAKE_INHERIT_PAYLOAD="$TMP_ROOT/inherit.payload" \
  FM_FAKE_LAUNCH_ENTERED="$TMP_ROOT/launch.entered" \
  FM_FAKE_LAUNCH_RELEASE="$TMP_ROOT/launch.release" \
  FM_SEND_SETTLE=0 FM_SEND_SLEEP=0 FM_REMOTE_REPLY_WAIT_SECONDS=10 \
  "$@"
}

sha256_file() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'; else sha256sum "$1" | awk '{print $1}'; fi
}

# The correlation token of the newest record in the remote secondmate's
# steering inbox: a remote steer is delivered as a durable record there, so
# the corr a reply must echo is read from the record body, never from typed
# pane bytes.
newest_remote_inbox_corr() {
  grep -Eoh 'corr=[a-f0-9]{16}' "$REMOTE_HOME"/state/parent-route/ios.inbox/*.msg 2>/dev/null \
    | tail -1 | cut -d= -f2-
}

seed_env() {
  FM_HOME="$TMP_ROOT/seed-parent" \
  FM_ROOT_OVERRIDE="$REMOTE_ROOT" \
  FM_PROCEVENT_CLAIM_ROOT="$CLAIMS" \
  FM_SSH_BIN="$FAKEBIN/fake-ssh" \
  FM_FAKE_SSH_COUNT="$SSH_COUNT" \
  FM_FAKE_REMOTE_ENTRYPOINT="$REMOTE_ROOT/bin/fm-remote-entrypoint.sh" \
  FM_REMOTE_JOB_PLATFORM_OVERRIDE=Linux \
  FM_REMOTE_JOB_STATE_ROOT="$TMP_ROOT/remote-jobs" \
  FM_FAKE_SSH_MODE="${FM_FAKE_SSH_MODE:-normal}" \
  FM_FAKE_REMOTE_CWD="$TMP_ROOT" \
  FM_FAKE_SEED_ENTERED="$TMP_ROOT/seed.entered" \
  FM_FAKE_SEED_RELEASE="$TMP_ROOT/seed.release" \
  FM_FAKE_DOCTOR_LOG="$DOCTOR_LOG" \
  FM_FAKE_DOCTOR_REPAIRED="$TMP_ROOT/doctor.repaired" \
  "$@"
}

REAL_GIT=$(command -v git)
cat > "$FAKEBIN/git" <<SH
#!/usr/bin/env bash
if [ "\${1:-}" = clone ] && [ "\${!#}" = "$TMP_ROOT/concurrent-home" ]; then
  printf 'clone\n' >> "$TMP_ROOT/provision-clones"
  if mkdir "$TMP_ROOT/provision-first" 2>/dev/null; then
    touch "$TMP_ROOT/provision.entered"
    while [ ! -f "$TMP_ROOT/provision.release" ]; do sleep 0.02; done
  fi
fi
exec "$REAL_GIT" "\$@"
SH
chmod +x "$FAKEBIN/git"
printf 'schema=fm-remote-home-provision.v1\nid_b64=%s\ncharter_b64=%s\nproject_count=0\n' \
  "$(printf ios | base64 | tr -d '\n')" \
  "$(printf 'Concurrent provisioning charter.\n' | base64 | tr -d '\n')" \
  > "$TMP_ROOT/provision.manifest"
PATH="$FAKEBIN:$PATH" FM_HOME="$TMP_ROOT/concurrent-home" FM_ROOT_OVERRIDE="$REMOTE_ROOT" \
  "$REMOTE_ROOT/bin/fm-remote-home-provision.sh" < "$TMP_ROOT/provision.manifest" \
  > "$TMP_ROOT/provision-one.out" 2>&1 &
provision_one=$!
provision_wait=0
while [ ! -f "$TMP_ROOT/provision.entered" ]; do
  kill -0 "$provision_one" 2>/dev/null || fail "first provisioning attempt exited before cloning"
  provision_wait=$((provision_wait + 1))
  [ "$provision_wait" -le 250 ] || fail "first provisioning attempt never reached cloning"
  sleep 0.02
done
PATH="$FAKEBIN:$PATH" FM_HOME="$TMP_ROOT/concurrent-home" FM_ROOT_OVERRIDE="$REMOTE_ROOT" \
  "$REMOTE_ROOT/bin/fm-remote-home-provision.sh" < "$TMP_ROOT/provision.manifest" \
  > "$TMP_ROOT/provision-two.out" 2>&1 &
provision_two=$!
sleep 0.2
[ "$(grep -cF clone "$TMP_ROOT/provision-clones")" -eq 1 ] \
  || fail "overlapping provisioning reached home classification concurrently"
touch "$TMP_ROOT/provision.release"
wait "$provision_one" || fail "first serialized provisioning attempt failed"
wait "$provision_two" || fail "reconciled provisioning attempt failed"
[ "$(cat "$TMP_ROOT/concurrent-home/.fm-secondmate-home")" = ios ] \
  || fail "serialized provisioning lost the published home"
[ "$(grep -cF clone "$TMP_ROOT/provision-clones")" -eq 1 ] \
  || fail "reconciled provisioning cloned the already-published home"
pass "overlapping remote home provisioning serializes through publication and rollback"
if [ "${FM_TEST_PROVISION_ONLY:-0}" = 1 ]; then
  echo "ALL TESTS PASSED"
  exit 0
fi

mkdir -p "$TMP_ROOT/seed-parent/data" "$TMP_ROOT/seed-parent/state"
FM_SECONDMATE_CHARTER='Failing seed charter.' FM_SECONDMATE_SCOPE='failed seed' \
  FM_FAKE_SSH_MODE=provision-block-fail seed_env "$ROOT/bin/fm-remote-home-seed.sh" \
  seed-fail remote-mac "$REMOTE_ROOT" "$TMP_ROOT/seed-fail-home" --no-projects \
  > "$TMP_ROOT/seed-fail.out" 2>&1 &
seed_fail_pid=$!
seed_wait=0
while [ ! -f "$TMP_ROOT/seed.entered" ]; do
  kill -0 "$seed_fail_pid" 2>/dev/null || fail "failing seed exited before remote provisioning"
  seed_wait=$((seed_wait + 1))
  [ "$seed_wait" -le 250 ] || fail "failing seed never reached remote provisioning"
  sleep 0.02
done
FM_SECONDMATE_CHARTER='Successful seed charter.' FM_SECONDMATE_SCOPE='successful seed' \
  seed_env "$ROOT/bin/fm-remote-home-seed.sh" seed-keep remote-mac "$REMOTE_ROOT" \
  "$TMP_ROOT/seed-keep-home" --no-projects > "$TMP_ROOT/seed-keep.out" 2>&1 &
seed_keep_pid=$!
sleep 0.2
kill -0 "$seed_keep_pid" 2>/dev/null || fail "competing seed bypassed the shared registry transaction"
touch "$TMP_ROOT/seed.release"
if wait "$seed_fail_pid"; then
  fail "known-failing seed unexpectedly succeeded"
fi
wait "$seed_keep_pid" || fail "serialized successful seed failed"
assert_no_grep '- seed-fail ' "$TMP_ROOT/seed-parent/data/secondmates.md" "failed seed route survived rollback"
assert_grep '- seed-keep ' "$TMP_ROOT/seed-parent/data/secondmates.md" "failed seed rollback removed a competing successful route"
assert_present "$TMP_ROOT/seed-keep-home/.fm-secondmate-home" "serialized seed lost its published remote home"
pass "remote seed rollback preserves serialized competing routes"

: > "$DOCTOR_LOG"
if FM_SECONDMATE_CHARTER='Unknown readiness charter.' FM_SECONDMATE_SCOPE='unknown readiness' \
  FM_FAKE_SSH_MODE=doctor-fix-unknown seed_env "$ROOT/bin/fm-remote-home-seed.sh" \
  seed-unknown remote-mac "$REMOTE_ROOT" "$TMP_ROOT/seed-unknown-home" --no-projects \
  > "$TMP_ROOT/seed-unknown.out" 2>&1; then
  fail "seeding claimed success after readiness repair completion became unknown"
fi
assert_grep 'remote readiness completion is unknown' "$TMP_ROOT/seed-unknown.out" \
  "unknown readiness did not report its distinct completion state"
assert_grep '- seed-unknown ' "$TMP_ROOT/seed-parent/data/secondmates.md" \
  "unknown readiness removed the registered route"
assert_present "$TMP_ROOT/seed-parent/data/seed-unknown/brief.md" \
  "unknown readiness removed the scaffolded brief"
assert_absent "$TMP_ROOT/seed-unknown-home" \
  "unknown readiness proceeded into remote home provisioning"
[ "$(cat "$DOCTOR_LOG")" = 'doctor-fix-unknown -
doctor-fix-unknown --fix' ] || fail "unknown readiness did not occur during the repair stage"$'\n'"$(cat "$DOCTOR_LOG")"
pass "unknown readiness preserves its route and brief for reconciliation"

# A host that cannot hold a durable second mate must be rejected by the
# readiness gate before any home is created on it, and the operator must get the
# gap text rather than a bare refusal.
: > "$DOCTOR_LOG"
if FM_SECONDMATE_CHARTER='Unready host charter.' FM_SECONDMATE_SCOPE='unready host' \
  FM_FAKE_SSH_MODE=doctor-human seed_env "$ROOT/bin/fm-remote-home-seed.sh" \
  seed-toolless remote-mac "$REMOTE_ROOT" "$TMP_ROOT/seed-toolless-home" --no-projects \
  > "$TMP_ROOT/seed-toolless.out" 2>&1; then
  fail "seeding proceeded against a host that is not ready for a remote second mate"
fi
assert_grep 'check gui-session=human:' \
  "$TMP_ROOT/seed-toolless.out" "the seed hid the remaining human gap"
assert_grep 'action: gui-session:' \
  "$TMP_ROOT/seed-toolless.out" "the seed hid the operator step that closes the gap"
assert_grep 'remote runtime preflight failed' "$TMP_ROOT/seed-toolless.out" \
  "the seed did not report the failing stage"
assert_absent "$TMP_ROOT/seed-toolless-home" "the seed provisioned a home despite a failing preflight"
assert_no_grep '- seed-toolless ' "$TMP_ROOT/seed-parent/data/secondmates.md" \
  "the refused route survived the preflight rollback"
assert_absent "$TMP_ROOT/seed-parent/data/seed-toolless/brief.md" \
  "the refused route left its scaffolded charter behind"
[ "$(cat "$DOCTOR_LOG")" = 'doctor-human -
doctor-human --fix
doctor-human -' ] || fail "the seed did not run the check, repair, re-check sequence"$'\n'"$(cat "$DOCTOR_LOG")"
pass "remote seeding checks, repairs, and re-checks readiness, then stops on a remaining gap"

# The same gate must accept a host whose only gaps were repairable.
: > "$DOCTOR_LOG"
rm -f "$TMP_ROOT/doctor.repaired"
out=$(FM_SECONDMATE_CHARTER='Repairable host charter.' FM_SECONDMATE_SCOPE='repairable host' \
  FM_FAKE_SSH_MODE=doctor-fixable seed_env "$ROOT/bin/fm-remote-home-seed.sh" \
  seed-repair remote-mac "$REMOTE_ROOT" "$TMP_ROOT/seed-repair-home" --no-projects 2>&1) \
  || fail "seeding refused a host whose gaps the repair closed"$'\n'"$out"
assert_present "$TMP_ROOT/seed-repair-home/.fm-secondmate-home" "the repaired host was never provisioned"
assert_grep '- seed-repair ' "$TMP_ROOT/seed-parent/data/secondmates.md" "the repaired route was not registered"
[ "$(cat "$DOCTOR_LOG")" = 'doctor-fixable -
doctor-fixable --fix
doctor-fixable -' ] || fail "the repaired seed did not re-check after its repair"$'\n'"$(cat "$DOCTOR_LOG")"
pass "remote seeding proceeds once the repair closes every gap"

# Seeding must not need a copy of the project in this home: firstmate names the
# origin it already resolved, the seed validates and transports it, and the
# primary project tree is left exactly as it was found.
projects_snapshot() { # <dir>
  local dir=$1 path
  (
    cd "$dir" 2>/dev/null || exit 0
    find . -print | LC_ALL=C sort | while IFS= read -r path; do
      if [ -f "$path" ] && [ ! -L "$path" ]; then
        printf '%s %s\n' "$path" "$(sha256_file "$path")"
      else
        printf '%s\n' "$path"
      fi
    done
  )
}
mkdir -p "$TMP_ROOT/seed-parent/projects"
fm_git_init_commit "$TMP_ROOT/seed-parent/projects/resident"
git init -q --bare "$TMP_ROOT/beta.git"
fm_git_init_commit "$TMP_ROOT/beta-src"
git -C "$TMP_ROOT/beta-src" remote add origin "file://$TMP_ROOT/beta.git"
git -C "$TMP_ROOT/beta-src" push -q -u origin HEAD
rm -rf "$TMP_ROOT/beta-src"
cat > "$TMP_ROOT/seed-parent/data/projects.md" <<'EOF'
- beta [direct-PR] - beta project (added 2026-08-06)
- delta [local-only] - delta project (added 2026-08-06)
EOF
BETA_ORIGIN="file://$TMP_ROOT/beta.git"
PROJECTS_BEFORE=$(projects_snapshot "$TMP_ROOT/seed-parent/projects")

if FM_SECONDMATE_CHARTER='Unsupplied origin charter.' FM_SECONDMATE_SCOPE='unsupplied origin' \
  seed_env "$ROOT/bin/fm-remote-home-seed.sh" seed-noorigin remote-mac "$REMOTE_ROOT" \
  "$TMP_ROOT/seed-noorigin-home" beta > "$TMP_ROOT/seed-noorigin.out" 2>&1; then
  fail "seeding an uncloned project with no origin claimed success"
fi
assert_grep 'pass beta=<origin-url>' "$TMP_ROOT/seed-noorigin.out" \
  "the refusal did not name how to supply the origin"
assert_absent "$TMP_ROOT/seed-noorigin-home" "the unresolvable origin still provisioned a remote home"

if FM_SECONDMATE_CHARTER='Unsafe origin charter.' FM_SECONDMATE_SCOPE='unsafe origin' \
  seed_env "$ROOT/bin/fm-remote-home-seed.sh" seed-unsafe remote-mac "$REMOTE_ROOT" \
  "$TMP_ROOT/seed-unsafe-home" 'beta=ext::git-upload-pack' \
  > "$TMP_ROOT/seed-unsafe.out" 2>&1; then
  fail "seeding accepted a remote-helper origin the remote host would execute"
fi
assert_grep 'not an accepted clone URL' "$TMP_ROOT/seed-unsafe.out" \
  "the unsafe-origin refusal did not name the reason"
assert_absent "$TMP_ROOT/seed-unsafe-home" "the unsafe origin still provisioned a remote home"

if FM_SECONDMATE_CHARTER='Local-only charter.' FM_SECONDMATE_SCOPE='local only' \
  seed_env "$ROOT/bin/fm-remote-home-seed.sh" seed-localonly remote-mac "$REMOTE_ROOT" \
  "$TMP_ROOT/seed-localonly-home" "delta=$BETA_ORIGIN" \
  > "$TMP_ROOT/seed-localonly.out" 2>&1; then
  fail "a supplied origin bypassed the local-only delivery-mode refusal"
fi
assert_grep 'is local-only and cannot be provisioned remotely' "$TMP_ROOT/seed-localonly.out" \
  "the local-only refusal did not name the registered mode"

if FM_SECONDMATE_CHARTER='Unregistered charter.' FM_SECONDMATE_SCOPE='unregistered' \
  seed_env "$ROOT/bin/fm-remote-home-seed.sh" seed-unregistered remote-mac "$REMOTE_ROOT" \
  "$TMP_ROOT/seed-unregistered-home" "gamma=$BETA_ORIGIN" \
  > "$TMP_ROOT/seed-unregistered.out" 2>&1; then
  fail "a supplied origin bypassed the project registry requirement"
fi
assert_grep 'has no registry record' "$TMP_ROOT/seed-unregistered.out" \
  "the unregistered-project refusal did not name the missing record"

out=$(FM_SECONDMATE_CHARTER='Own beta delivery on the build Mac.' \
  FM_SECONDMATE_SCOPE='beta delivery and validation' \
  seed_env "$ROOT/bin/fm-remote-home-seed.sh" seed-noclone remote-mac "$REMOTE_ROOT" \
  "$TMP_ROOT/seed-noclone-home" "beta=$BETA_ORIGIN" 2>&1) \
  || fail "seeding refused a registered project whose origin was supplied"$'\n'"$out"
assert_contains "$out" "home=remote-mac:$TMP_ROOT/seed-noclone-home" \
  "the no-clone seed did not report the host-qualified home"
assert_grep '- seed-noclone ' "$TMP_ROOT/seed-parent/data/secondmates.md" \
  "the no-clone seed did not register the remote route"
assert_present "$TMP_ROOT/seed-noclone-home/projects/beta/README.md" \
  "the remote host did not clone the supplied origin"
[ "$(git -C "$TMP_ROOT/seed-noclone-home/projects/beta" remote get-url origin)" = "$BETA_ORIGIN" ] \
  || fail "the remote clone did not come from the supplied origin"
assert_grep '- beta [direct-PR]' "$TMP_ROOT/seed-noclone-home/data/projects.md" \
  "the remote home did not publish the project's registered posture"
assert_absent "$TMP_ROOT/seed-parent/projects/beta" \
  "seeding cloned the project into the primary project tree"
[ "$(projects_snapshot "$TMP_ROOT/seed-parent/projects")" = "$PROJECTS_BEFORE" ] \
  || fail "seeding changed the primary project tree"
pass "remote seeding provisions a supplied origin without touching the primary project tree"

# The receiving host validates the origin itself rather than trusting whatever
# reached it, so a manifest naming an executable transport provisions nothing.
printf 'schema=fm-remote-home-provision.v1\nid_b64=%s\ncharter_b64=%s\nproject_count=1\nproject=%s|%s|%s|%s\n' \
  "$(printf unsafe-origin | base64 | tr -d '\n')" \
  "$(printf 'Unsafe origin manifest charter.\n' | base64 | tr -d '\n')" \
  "$(printf beta | base64 | tr -d '\n')" \
  "$(printf 'ext::git-upload-pack' | base64 | tr -d '\n')" \
  "$(printf -- '- beta [direct-PR] - beta project (added 2026-08-06)' | base64 | tr -d '\n')" \
  "$(printf direct-PR | base64 | tr -d '\n')" \
  > "$TMP_ROOT/unsafe-origin.manifest"
if FM_HOME="$TMP_ROOT/unsafe-origin-home" FM_ROOT_OVERRIDE="$REMOTE_ROOT" \
  "$REMOTE_ROOT/bin/fm-remote-home-provision.sh" < "$TMP_ROOT/unsafe-origin.manifest" \
  > "$TMP_ROOT/unsafe-origin.out" 2>&1; then
  fail "remote provisioning accepted an origin the transport had not validated"
fi
assert_grep 'not an accepted clone URL' "$TMP_ROOT/unsafe-origin.out" \
  "remote provisioning did not name the rejected origin"
assert_absent "$TMP_ROOT/unsafe-origin-home" "the rejected manifest left a remote home behind"
pass "remote provisioning re-validates a supplied origin at the receiving host"

# Firstmate is a shared template, so seeding must carry a project origin from any
# forge or host, not a privileged one. These four URL shapes have to survive the
# parent's validation, the manifest, the transport, and the receiving host's own
# validation, and arrive at git unchanged. A fixture resolver records the exact
# clone source the remote side hands to git and then serves it from a local bare
# repository, because an offline run cannot reach bitbucket.org itself.
FORGE_CLONE_LOG="$TMP_ROOT/forge-clone.log"
FORGE_ORIGIN_MAP="$TMP_ROOT/forge-origin.map"
: > "$FORGE_CLONE_LOG"
: > "$FORGE_ORIGIN_MAP"
forge_project() { # <project> <origin-url>
  local project=$1 origin=$2 tab
  tab=$(printf '\t')
  fm_git_init_commit "$TMP_ROOT/forge-src-$project"
  printf 'served from %s\n' "$origin" > "$TMP_ROOT/forge-src-$project/ORIGIN.txt"
  git -C "$TMP_ROOT/forge-src-$project" add ORIGIN.txt
  git -C "$TMP_ROOT/forge-src-$project" \
    -c user.name='Firstmate Tests' -c user.email='tests@example.invalid' commit -qm origin
  git clone --quiet --bare "$TMP_ROOT/forge-src-$project" "$TMP_ROOT/forge-$project.git"
  rm -rf "$TMP_ROOT/forge-src-$project"
  printf '%s%s%s\n' "$origin" "$tab" "$TMP_ROOT/forge-$project.git" >> "$FORGE_ORIGIN_MAP"
  printf -- '- %s [direct-PR] - %s project (added 2026-08-06)\n' "$project" "$project" \
    >> "$TMP_ROOT/seed-parent/data/projects.md"
}
forge_project bitbucket-app 'https://bitbucket.org/team/bitbucket-app.git'
forge_project ghe-app 'https://git.example.com/org/ghe-app.git'
forge_project gitlab-app 'ssh://git@gitlab.self.hosted:2222/group/subgroup/gitlab-app.git'
forge_project scp-app 'git@host.internal:group/scp-app.git'

cat > "$REMOTE_ROOT/bin/git" <<SH
#!/usr/bin/env bash
# Fixture origin resolver for the remote side: record the clone source exactly as
# the production code hands it to git, then serve any recorded URL from a local
# bare repository so the run stays offline. Everything else is real git.
set -u
if [ "\${1:-}" = clone ]; then
  printf '%s\n' "\$*" >> '$FORGE_CLONE_LOG'
  args=()
  for arg in "\$@"; do
    replacement=\$(awk -v k="\$arg" -F'\t' '\$1 == k { print \$2; exit }' '$FORGE_ORIGIN_MAP' 2>/dev/null)
    if [ -n "\$replacement" ]; then args+=("\$replacement"); else args+=("\$arg"); fi
  done
  exec '$REAL_GIT' "\${args[@]}"
fi
exec '$REAL_GIT' "\$@"
SH
chmod +x "$REMOTE_ROOT/bin/git"

FORGE_HOME="$TMP_ROOT/seed-forge-home"
out=$(FM_SECONDMATE_CHARTER='Own delivery for projects hosted anywhere.' \
  FM_SECONDMATE_SCOPE='multi-forge delivery' \
  seed_env "$ROOT/bin/fm-remote-home-seed.sh" seed-forge remote-mac "$REMOTE_ROOT" \
  "$FORGE_HOME" \
  'bitbucket-app=https://bitbucket.org/team/bitbucket-app.git' \
  'ghe-app=https://git.example.com/org/ghe-app.git' \
  'gitlab-app=ssh://git@gitlab.self.hosted:2222/group/subgroup/gitlab-app.git' \
  'scp-app=git@host.internal:group/scp-app.git' 2>&1) \
  || fail "seeding refused origins hosted outside GitHub"$'\n'"$out"

while IFS="$(printf '\t')" read -r forge_origin _; do
  [ -n "$forge_origin" ] || continue
  assert_grep "$forge_origin" "$FORGE_CLONE_LOG" \
    "the remote host did not clone from the supplied origin $forge_origin"
done < "$FORGE_ORIGIN_MAP"
for forge_project_name in bitbucket-app ghe-app gitlab-app scp-app; do
  assert_present "$FORGE_HOME/projects/$forge_project_name/.git" \
    "the remote home has no clone for $forge_project_name"
  assert_grep "$forge_project_name" "$FORGE_HOME/data/projects.md" \
    "the remote registry omitted $forge_project_name"
  assert_absent "$TMP_ROOT/seed-parent/projects/$forge_project_name" \
    "seeding $forge_project_name cloned it into the primary project tree"
done
# Each clone must carry its own origin's content, so one shared fixture repo
# cannot make a mismatched route look routed.
[ "$(cat "$FORGE_HOME/projects/bitbucket-app/ORIGIN.txt")" = \
  'served from https://bitbucket.org/team/bitbucket-app.git' ] \
  || fail "the bitbucket route did not clone its own origin"
[ "$(cat "$FORGE_HOME/projects/scp-app/ORIGIN.txt")" = \
  'served from git@host.internal:group/scp-app.git' ] \
  || fail "the scp-like route did not clone its own origin"
[ "$(projects_snapshot "$TMP_ROOT/seed-parent/projects")" = "$PROJECTS_BEFORE" ] \
  || fail "seeding non-GitHub projects changed the primary project tree"
assert_grep '- seed-forge ' "$TMP_ROOT/seed-parent/data/secondmates.md" \
  "the multi-forge route was not registered"

rm -f "$REMOTE_ROOT/bin/git"
[ -z "$(git -C "$REMOTE_ROOT" status --porcelain)" ] \
  || fail "the fixture origin resolver was left behind in the remote code root"
pass "seeding carries bitbucket, self-hosted, and scp-like origins through to the remote clone"

# Provision and register the remote route from the captain-facing primary.
out=$(FM_SECONDMATE_CHARTER='Own iOS delivery on the build Mac.' \
  FM_SECONDMATE_SCOPE='iOS implementation and Xcode validation' \
  remote_env "$ROOT/bin/fm-remote-home-seed.sh" ios remote-mac "$REMOTE_ROOT" "$REMOTE_HOME" alpha)
assert_contains "$out" "home=remote-mac:$REMOTE_HOME" "remote seed did not report the host-qualified home"
assert_grep 'host: remote-mac; root:' "$PARENT/data/secondmates.md" "registry did not record the remote host dimension"
assert_present "$REMOTE_HOME/.fm-secondmate-home" "remote provisioning did not publish the identity marker"
printf 'ALPHA_EVIDENCE origin_HEAD=%s checkout_HEAD=%s\n' "$(git --git-dir="$TMP_ROOT/alpha.git" symbolic-ref HEAD)" "$(git -C "$REMOTE_HOME/projects/alpha" symbolic-ref HEAD)"
if [ -d "$REMOTE_HOME/projects/alpha/.git" ]; then printf 'ALPHA_EVIDENCE .git=present\n'; fi
if [ -f "$REMOTE_HOME/projects/alpha/README.md" ]; then
  printf 'ALPHA_EVIDENCE README.md='; cat "$REMOTE_HOME/projects/alpha/README.md"
  git -C "$REMOTE_HOME/projects/alpha" diff --exit-code HEAD -- README.md || fail "checkout README differs from committed README"
else
  printf 'ALPHA_EVIDENCE README.md=absent\n'
fi
printf 'BETA_EVIDENCE origin_HEAD=%s checkout_HEAD=%s README.md=' "$(git --git-dir="$TMP_ROOT/beta.git" symbolic-ref HEAD)" "$(git -C "$TMP_ROOT/seed-noclone-home/projects/beta" symbolic-ref HEAD)"
cat "$TMP_ROOT/seed-noclone-home/projects/beta/README.md"
assert_present "$REMOTE_HOME/projects/alpha/README.md" "remote provisioning did not clone the project on that host"
assert_grep "$REMOTE_HOME/state/parent-replies.status" "$REMOTE_HOME/data/charter.md" "remote charter did not use its append-only reply log"
assert_no_grep "$PARENT/state/ios.status" "$REMOTE_HOME/data/charter.md" "remote charter retained the inaccessible local status path"
if FM_SECONDMATE_CHARTER='Own iOS delivery on the build Mac.' \
  FM_SECONDMATE_SCOPE='iOS implementation and Xcode validation' \
  remote_env "$ROOT/bin/fm-remote-home-seed.sh" ios remote-mac "$REMOTE_ROOT" "$TMP_ROOT/other-home" alpha \
  >/dev/null 2>&1; then
  fail "remote seed allowed an existing id to move to another home"
fi
assert_grep "home: $REMOTE_HOME" "$PARENT/data/secondmates.md" "refused remote reassignment changed the durable route"
pass "remote seed registers the route and provisions the whole home and project clone on that host"
printf "TARGETED_ALPHA_PREFIX_COMPLETE\n"
