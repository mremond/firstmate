from pathlib import Path
import os, subprocess, json, hashlib, signal
root = Path.cwd()
lab = root / '.test-phase/guard'
lab.mkdir(parents=True, exist_ok=True)
evidence = Path('/Users/mremond/.no-mistakes/evidence/01M2082V2RRVRBS459RBJ4K0BY')
# DEBUG intercepts the first case invocation, after the actual suite installs
# its functions and EXIT trap. The suite file and its teardown stay unchanged.
(lab/'bootstrap.sh').write_text('''unset BASH_ENV
trap 'if [ "$BASH_COMMAND" = test_fixture_root_gone_after_normal_exit ]; then trap - DEBUG; . "$FM_GUARD_ACTIONS"; fi' DEBUG
''')
(lab/'actions.sh').write_text('''probe_root=$(fm_test_tmproot fm-guard-probe)
if [ "$FM_GUARD_MODE" = own ]; then
  sleep 120 &
  HELD_LISTENER_CHILD=$!
else
  HELD_LISTENER_CHILD=$FM_GUARD_FOREIGN_PID
fi
parent=$(ps -o ppid= -p "$HELD_LISTENER_CHILD" | tr -d '[:space:]')
allowed=false
held_listener_child_is_ours && allowed=true
printf '%s\\n%s\\n%s\\n%s\\n%s\\n' "$$" "$HELD_LISTENER_CHILD" "$parent" "$allowed" "$probe_root" > "$FM_GUARD_STATE"
printf 'suite_pid=%s tracked_pid=%s observed_parent=%s guard_permits=%s fixture=%s\\n' "$$" "$HELD_LISTENER_CHILD" "$parent" "$allowed" "$probe_root"
# Run the suite's actual EXIT trap. Parent verifies effects after wait().
exit 0
''')
def alive(pid):
    try: os.kill(pid,0); return True
    except ProcessLookupError: return False
foreign=subprocess.Popen(['sleep','120'])
try:
    print('target=3cea357284a5419aeacb0ad823b6e48091a4f826',flush=True)
    print('suite_sha256='+hashlib.sha256((root/'tests/fm-test-fixture-cleanup.test.sh').read_bytes()).hexdigest(),flush=True)
    print(f'probe_parent={os.getpid()} foreign_sleep_pid={foreign.pid}',flush=True)
    for mode in ['own','foreign']:
        state=lab/(mode+'.state')
        tmp=lab/(mode+'-tmp');tmp.mkdir()
        env=os.environ.copy()
        env.update(BASH_ENV=str(lab/'bootstrap.sh'),FM_GUARD_ACTIONS=str(lab/'actions.sh'),FM_GUARD_MODE=mode,FM_GUARD_FOREIGN_PID=str(foreign.pid),FM_GUARD_STATE=str(state),TMPDIR=str(tmp))
        proc=subprocess.Popen(['bash','tests/fm-test-fixture-cleanup.test.sh'],env=env)
        code=proc.wait(timeout=120)
        suite,pid,parent,allowed,fixture=state.read_text().splitlines()
        pid=int(pid)
        post=alive(pid)
        print(f'mode={mode} suite_exit={code} tracked_pid={pid} alive_after_teardown={str(post).lower()} fixture_exists_after_teardown={Path(fixture).exists()}',flush=True)
        assert code==0 and not Path(fixture).exists()
        if mode=='own': assert int(parent)==proc.pid and allowed=='true' and not post
        else: assert int(parent)!=proc.pid and allowed=='false' and post and foreign.poll() is None
finally:
    if foreign.poll() is None: foreign.terminate()
    foreign.wait(timeout=10)
    print(f'probe_cleanup foreign_sleep_pid={foreign.pid} reaped=true',flush=True)
