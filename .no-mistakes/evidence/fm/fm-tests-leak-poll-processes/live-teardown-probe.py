from pathlib import Path
import os, subprocess, json, time, signal, datetime
root=Path.cwd(); lab=root/'.test-phase/live-probes'; lab.mkdir(parents=True,exist_ok=True)
evidence=Path('/Users/mremond/.no-mistakes/evidence/01M2082V2RRVRBS459RBJ4K0BY')
# Intercept the public suite after its real board build returned with a listener.
# Only control the stimulus; execute its unchanged installed teardown traps.
(lab/'bootstrap.sh').write_text('''unset BASH_ENV
trap 'case "$BASH_COMMAND" in url=*) trap - DEBUG; . "$FM_LIVE_ACTIONS" ;; esac' DEBUG
''')
(lab/'actions.sh').write_text('''printf '%s\\n%s\\n' "$LAB" "$BOARD" > "$FM_LIVE_READY"
while [ ! -f "$FM_LIVE_RELEASE" ]; do sleep 0.1; done
fail "probe: deliberate assertion failure with a real Lavish poll armed"
''')
def polls(target):
    out=[]
    for line in subprocess.check_output(['ps','-axo','pid=,ppid=,pgid=,args='],text=True).splitlines():
        cols=line.strip().split(None,3)
        if len(cols)!=4:continue
        args=cols[3]
        if ('fm-procevent-lavish.sh poll '+target in args or 'lavish-axi poll '+target in args) and not args.startswith('/bin/zsh -c'):
            out.append(dict(pid=int(cols[0]),ppid=int(cols[1]),pgid=int(cols[2]),args=args))
    return out
for mode in ['failure','sigterm']:
    case=lab/mode; case.mkdir(); (case/'tmp').mkdir()
    env=os.environ.copy(); env.update(json.loads((root/'.test-phase/lavish-env.json').read_text()))
    env.update(TMPDIR=str(case/'tmp'),BASH_ENV=str(lab/'bootstrap.sh'),FM_LIVE_ACTIONS=str(lab/'actions.sh'),FM_LIVE_READY=str(case/'ready'),FM_LIVE_RELEASE=str(case/'release'))
    with (evidence/f'live-{mode}-suite.log').open('w') as transcript:
        proc=subprocess.Popen(['bash','tests/fm-bearings-board-lavish-live-e2e.test.sh'],env=env,stdout=transcript,stderr=subprocess.STDOUT)
        print(json.dumps(dict(mode=mode,event='start',suite_pid=proc.pid)),flush=True)
        target=None
        try:
            end=time.monotonic()+600
            while not (case/'ready').exists():
                if proc.poll() is not None:raise RuntimeError(f'{mode}: suite exited {proc.returncode} before live checkpoint')
                if time.monotonic()>end:raise TimeoutError('real board build did not reach checkpoint')
                time.sleep(.2)
            home,target=(case/'ready').read_text().splitlines()
            end=time.monotonic()+60
            before=[]
            while time.monotonic()<end:
                before=polls(target)
                if any(row['args'].startswith('node ') and 'lavish-axi poll ' in row['args'] for row in before):break
                time.sleep(.2)
            assert Path(target).exists() and before
            assert any(row['args'].startswith('node ') and 'lavish-axi poll ' in row['args'] for row in before), 'real lavish-axi poll was not observed'
            print(json.dumps(dict(mode=mode,event='armed',suite_pid=proc.pid,target=target,target_exists=True,polls=before)),flush=True)
            if mode=='failure':(case/'release').touch()
            else:proc.send_signal(signal.SIGTERM)
            code=proc.wait(timeout=180)
            after=polls(target)
            states=[]
            for row in before:
                state=subprocess.run(['ps','-p',str(row['pid']),'-o','pid=,ppid=,args='],text=True,capture_output=True)
                states.append(dict(pid=row['pid'],ps_exit=state.returncode,current=state.stdout.strip()))
            print(json.dumps(dict(mode=mode,event='after_teardown',suite_exit=code,target_exists=Path(target).exists(),home_exists=Path(home).exists(),surviving_polls=after,recorded_pid_postconditions=states)),flush=True)
            assert code==(1 if mode=='failure' else 143)
            assert not Path(home).exists() and not Path(target).exists() and not after
        finally:
            if proc.poll() is None:
                proc.terminate(); proc.wait(timeout=180)
