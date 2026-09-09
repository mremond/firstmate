#!/usr/bin/env python3
"""Focused executable checks; temporary product copies stay inside the worktree.

Run from the submitted worktree: python3 <this-file> matrix|live.
Source text is used only to select executable tests and make deliberate mutants.
All verdicts come from running commands and observing their outputs and state.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path.cwd()
EVIDENCE = Path(__file__).parent
BASE = '40c50ea8843c5b6a5351db8352675537252b653e'
CASE = 'test_hook_no_afk_ignores_poll_derived_grace'
env = {k: v for k, v in os.environ.items()
       if not k.startswith(('FM_', 'GIT_', 'CLAUDE', 'CURSOR', 'GROK', 'CODEX_'))}
env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
           GIT_AUTHOR_NAME='test', GIT_AUTHOR_EMAIL='test@example.invalid',
           GIT_COMMITTER_NAME='test', GIT_COMMITTER_EMAIL='test@example.invalid')


def command(args, *, cwd=ROOT, extra=None, input=None, timeout=40):
    return subprocess.run([str(x) for x in args], cwd=cwd,
                          env=env | (extra or {}), input=input, text=True,
                          capture_output=True, timeout=timeout)


def definitions(text):
    # The suite has a list of bare function calls after its definitions.
    # Select the definitions, then execute named cases without walking the suite.
    return text.split('\ntest_predicate_healthy_no_inflight\n', 1)[0] + '\n'


def matrix(scratch):
    product = scratch / 'product'
    (product / 'tests').mkdir(parents=True)
    shutil.copytree(ROOT / 'bin', product / 'bin')
    shutil.copytree(ROOT / 'docs/supervision-protocols',
                    product / 'docs/supervision-protocols')
    shutil.copy2(ROOT / 'tests/lib.sh', product / 'tests/lib.sh')
    target = (ROOT / 'tests/fm-turnend-guard.test.sh').read_text()
    base = command(['git', 'show', f'{BASE}:tests/fm-turnend-guard.test.sh'])
    assert base.returncode == 0, base.stderr
    wake = (ROOT / 'bin/fm-wake-lib.sh').read_text()
    guard = (ROOT / 'bin/fm-turnend-guard.sh').read_text()
    remove_age = wake.replace('  [ "$age" -lt "$grace" ] || return 1\n',
                              '  : # mutation: remove watcher beacon-age rejection\n', 1)
    wider_grace = guard.replace('GRACE=${FM_GUARD_GRACE:-300}',
                                'GRACE=${FM_GUARD_GRACE:-660}', 1)
    results = []
    transcript = []

    def run(label, text, body, expected=0, wake_text=wake, guard_text=guard):
        (product / 'bin/fm-wake-lib.sh').write_text(wake_text)
        (product / 'bin/fm-turnend-guard.sh').write_text(guard_text)
        (product / 'tests/selected.sh').write_text(definitions(text) + body + '\n')
        run_env = {'TMPDIR': str(scratch)}
        trace = EVIDENCE / f'{label}.trace.log'
        with trace.open('w') as out:
            p = subprocess.run(['bash', '-c', 'exec 3>"$1"; export BASH_XTRACEFD=3; bash -x "$2"',
                                '_', str(trace), str(product / 'tests/selected.sh')],
                               cwd=product, env=env | run_env, text=True,
                               capture_output=True, timeout=45)
        entry = dict(name=label, expected_exit=expected, actual_exit=p.returncode,
                     stdout=p.stdout, stderr=p.stderr)
        results.append(entry)
        transcript.append(f'=== {label}: expected exit {expected}, actual {p.returncode} ===\n'
                          + p.stdout + p.stderr)
        print(transcript[-1], flush=True)
        assert p.returncode == expected, entry

    # Establish the reported masking condition before executing the repaired test.
    run('old-fixture-age-contrast', base.stdout, r'''
dir=$(make_away_home_between_cycles "$TMP_ROOT/old-contrast")
rm -f "$dir/state/.afk"
sleep 60 &
pid=$!
record_daemon_lock "$dir" "$pid" || fail 'daemon identity unavailable'
for age in 0 400; do
  fm_touch_epoch "$(( $(date +%s) - age ))" "$dir/state/.last-watcher-beat"
  out=$(FM_GUARD_GRACE='' FM_POLL=600 run_hook "$dir" false); status=$?
  printf 'old fixture: beacon_age=%s away=off daemon_lock=present watcher_lock=absent exit=%s\n%s\n' "$age" "$status" "$out"
  expect_code 2 "$status" 'old fixture blocks regardless of beacon age'
done
kill "$pid"; wait "$pid" 2>/dev/null || true
''')
    run('base-pristine', base.stdout, CASE)
    run('base-age-rejection-removed', base.stdout, CASE, wake_text=remove_age)
    run('target-age-rejection-removed', target, CASE, expected=1, wake_text=remove_age)
    run('target-wrong-660-second-grace', target, CASE, expected=1, guard_text=wider_grace)
    run('target-missing-watcher-control', target,
        'record_watcher_lock() { :; }\n' + CASE, expected=1)
    run('target-pristine', target, CASE)
    neighboring = [
        'test_hook_silent_with_live_lock_and_fresh_beacon',
        'test_hook_blocks_with_live_lock_and_stale_beacon',
        'test_hook_daemon_lock_is_ignored_without_away_mode',
        'test_hook_away_daemon_allows_beacon_within_poll_derived_grace',
        'test_hook_away_daemon_blocks_dead_daemon_despite_poll_derived_grace',
        'test_hook_away_daemon_blocks_beacon_older_than_poll_derived_grace']
    run('target-adjacent-boundaries', target, '\n'.join(neighboring))
    (EVIDENCE / 'mutation-matrix.json').write_text(json.dumps(results, indent=2) + '\n')
    (EVIDENCE / 'mutation-matrix.log').write_text('\n'.join(transcript))


def live(scratch):
    home = scratch / 'live-home'
    state = home / 'state'
    state.mkdir(parents=True)
    (home / 'config').mkdir()
    (home / 'data').mkdir()
    (home / 'AGENTS.md').write_text('')
    (home / 'bin').symlink_to(ROOT / 'bin', target_is_directory=True)
    p = command(['git', 'init', '-q', home])
    assert p.returncode == 0, p.stderr
    live_env = {'FM_HOME': str(home), 'FM_ROOT_OVERRIDE': str(home),
                'FM_STATE_OVERRIDE': str(state), 'FM_POLL': '600',
                'FM_GUARD_GRACE': '', 'TMPDIR': str(scratch), 'CLAUDECODE': '1'}
    # A real registered custom check gives the watcher useful work without an
    # agent session, a fabricated task record, or a fake watcher owner.
    check = state / 'beacon-verification.check.sh'
    check.write_text('#!/usr/bin/env bash\nprintf executed > "$FM_HOME/state/check-executed"\n')
    check.chmod(0o700)
    registered = command([ROOT / 'bin/fm-check-register.sh', 'beacon-verification'],
                         extra=live_env)
    assert registered.returncode == 0, registered.stderr
    transcript = ['COMMAND: bin/fm-check-register.sh beacon-verification\n' + registered.stdout]
    observations = []
    watcher_log = (EVIDENCE / 'real-watcher.log').open('w')
    watcher = subprocess.Popen([str(ROOT / 'bin/fm-watch.sh')], cwd=home,
                               env=env | live_env, stdout=watcher_log,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if (state / 'check-executed').exists() and (state / '.last-watcher-beat').exists():
                break
            assert watcher.poll() is None, 'real watcher exited before startup'
            time.sleep(0.1)
        assert (state / 'check-executed').read_text() == 'executed'
        # Confirm that the product itself published the ownership proof.
        lock = state / '.watch.lock'
        identity = (lock / 'pid-identity').read_text()
        pid = int((lock / 'pid').read_text())
        assert pid == watcher.pid
        process = command(['ps', '-p', str(pid), '-o', 'pid=,ppid=,lstart=,command='])
        transcript += ['COMMAND: bin/fm-watch.sh (FM_POLL=600, away mode off)\n',
                       'Product-owned lock:\n' + json.dumps({
                           x: (lock / x).read_text().strip()
                           for x in ['pid', 'fm-home', 'watcher-path', 'pid-identity']}, indent=2),
                       'Process proof:\n' + process.stdout]
        # Let the initial cycle reach its 600-second wait; the check's side
        # effect above proves the watcher is executing real registered work.
        time.sleep(1)

        def invoke(name, expected, age=None):
            beacon = state / '.last-watcher-beat'
            if age is not None:
                stamp = int(time.time()) - age
                os.utime(beacon, (stamp, stamp))
            measured_age = int(time.time()) - int(beacon.stat().st_mtime)
            p = command([ROOT / 'bin/fm-turnend-guard.sh'], cwd=home,
                        extra=live_env, input='{"stop_hook_active":false}')
            entry = dict(name=name, watcher_pid=pid, beacon_age=measured_age,
                         away_mode=False, poll_seconds=600, exit=p.returncode,
                         stdout=p.stdout, stderr=p.stderr)
            observations.append(entry)
            transcript.append('COMMAND: printf \'{"stop_hook_active":false}\' | '
                              'FM_GUARD_GRACE="" FM_POLL=600 bin/fm-turnend-guard.sh\n'
                              + json.dumps(entry, indent=2))
            print(json.dumps(entry), flush=True)
            assert p.returncode == expected, entry
            if expected == 0:
                assert not p.stdout and not p.stderr, entry
            else:
                assert 'watcher supervision needs Stop-owned automatic recovery' in p.stderr, entry
            assert watcher.poll() is None, 'watcher stopped during same-owner contrast'
            assert (lock / 'pid-identity').read_text() == identity
            return entry

        invoke('real watcher permits fresh beacon', 0)
        invoke('same real watcher blocks 400-second beacon despite FM_POLL=600', 2, 400)
        invoke('refreshing only beacon restores permission', 0, 0)
        # Reversibly hide the ownership lock to challenge the new fresh control.
        hidden = state / '.watch.saved'
        lock.rename(hidden)
        try:
            p = command([ROOT / 'bin/fm-turnend-guard.sh'], cwd=home,
                        extra=live_env, input='{"stop_hook_active":false}')
            entry = dict(name='fresh beacon without published watcher ownership blocks',
                         exit=p.returncode, stdout=p.stdout, stderr=p.stderr)
            observations.append(entry)
            transcript.append(json.dumps(entry, indent=2))
            print(json.dumps(entry), flush=True)
            assert p.returncode == 2, entry
        finally:
            hidden.rename(lock)
        invoke('restoring same ownership restores permission', 0, 0)
    finally:
        os.killpg(watcher.pid, signal.SIGTERM)
        try:
            watcher.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(watcher.pid, signal.SIGKILL)
            watcher.wait()
        watcher_log.close()
        (EVIDENCE / 'live-guard-transcript.log').write_text('\n\n'.join(transcript) + '\n')
        (EVIDENCE / 'live-guard-results.json').write_text(json.dumps(observations, indent=2) + '\n')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='.turnend-phase-', dir=ROOT) as tmp:
        scratch = Path(tmp)
        if sys.argv[1] == 'matrix':
            matrix(scratch)
        elif sys.argv[1] == 'live':
            live(scratch)
        else:
            raise SystemExit('expected matrix or live')
