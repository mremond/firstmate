import json, os, pathlib, shutil, signal, subprocess, time
ROOT = pathlib.Path.cwd()
EVIDENCE = pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M2JEJPE43XFXJCGYM3KFAX75')
LAB = ROOT / '.nm-test-phase' / 'live'
LAB.mkdir(parents=True, exist_ok=True)
LIB = ROOT / 'bin/fm-wake-lib.sh'
WATCH = ROOT / 'bin/fm-watch.sh'
procs = []
handles = []
results = []

def report(name, **fields):
    row = dict(scenario=name, **fields)
    results.append(row)
    print(json.dumps(row), flush=True)
    (EVIDENCE/'live-watcher-results.json').write_text(json.dumps(results, indent=2)+'\n')

def home(name):
    p=LAB/name
    for d in ('state','data','config','tmp'): (p/d).mkdir(parents=True, exist_ok=True)
    return p

def env(p, **extra):
    e={k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'TASKS_AXI_'))}
    e.update(FM_HOME=str(p), FM_STATE_OVERRIDE=str(p/'state'), FM_ROOT_OVERRIDE=str(ROOT),
             FM_GATE_REFUSE_BYPASS='1', TMPDIR=str(p/'tmp'), FM_POLL='0.1',
             FM_CHECK_INTERVAL='999999', FM_HEARTBEAT='999999', FM_SIGNAL_GRACE='0')
    e.update(extra)
    return e

def run(p, script, *args, timeout=10, **extra):
    return subprocess.run(['bash','-c',script,'_',str(LIB),*map(str,args)],env=env(p,**extra),cwd=p,
                          capture_output=True,text=True,timeout=timeout)

def spawn(p, args, label, **extra):
    out=open(EVIDENCE/(label+'.stdout.log'),'w'); err=open(EVIDENCE/(label+'.stderr.log'),'w')
    handles.extend([out,err])
    proc=subprocess.Popen(list(map(str,args)),env=env(p,**extra),cwd=p,stdout=out,stderr=err)
    procs.append(proc)
    return proc

def wait_until(test, timeout=12):
    start=time.monotonic()
    while time.monotonic()-start < timeout:
        if test(): return
        time.sleep(.03)
    raise AssertionError('condition did not become true within '+str(timeout)+'s')

def read(p):
    try: return p.read_text().strip()
    except FileNotFoundError: return ''

def ps(pid):
    return subprocess.run(['ps','-p',str(pid),'-o','pid=,ppid=,pgid=,stat=,command='],capture_output=True,text=True).stdout.strip()

def start(p,label,watch=WATCH,**extra):
    proc=spawn(p,[watch],label,**extra)
    wait_until(lambda: (p/'state/.last-watcher-beat').exists() and read(p/'state/.watch.lock/pid')==str(proc.pid))
    assert proc.poll() is None, 'watcher exited before test'
    return proc

def lock_holder(p,lock,label):
    ready=p/(label+'.ready')
    script='. "$1"; fm_lock_try_acquire "$2" || exit 11; trap \'fm_lock_release "$2"; exit\' TERM; echo ready > "$3"; while :; do sleep .1; done'
    proc=spawn(p,['bash','-c',script,'_',LIB,lock,ready],label)
    wait_until(lambda: ready.exists())
    return proc

def stop(proc,timeout=20):
    t=time.monotonic(); proc.send_signal(signal.SIGTERM); rc=proc.wait(timeout=timeout)
    return rc,round(time.monotonic()-t,3)

try:
    p=home('fallback-returned-check'); state=p/'state'
    custom=state/'custom.check.sh'
    custom.write_text('''#!/usr/bin/env bash
perl -e '$SIG{TERM}="IGNORE"; open my $r, ">", $ENV{LIVE_READY} or die $!; print {$r} "ready\\n"; close $r; select undef, undef, undef, 4; open my $s, ">", $ENV{LIVE_SENTINEL} or die $!; print {$s} "late\\n"; close $s; select undef, undef, undef, 1' &
printf '%s\\n' "$!" > "$LIVE_CHILD"
while [ ! -s "$LIVE_READY" ]; do sleep .01; done
: > "$LIVE_DONE"
'''); custom.chmod(0o700)
    registration=subprocess.run([str(ROOT/'bin/fm-check-register.sh'),'custom'],env=env(p),cwd=p,capture_output=True,text=True)
    assert registration.returncode==0, registration.stderr
    w=start(p,'fallback-returned',FM_CHECK_FORCE_FALLBACK='1',FM_CHECK_TIMEOUT='10',LIVE_READY=str(p/'ready'),LIVE_CHILD=str(p/'child.pid'),LIVE_DONE=str(p/'done'),LIVE_SENTINEL=str(p/'sentinel'))
    wait_until(lambda: (p/'done').exists() and (state/'.last-check').exists())
    child=int(read(p/'child.pid')); before=ps(w.pid)
    rc,elapsed=stop(w)
    child_state=ps(child)
    assert rc!=0 and elapsed<20
    assert not child_state or child_state.split()[3].startswith('Z'), child_state
    assert not (p/'sentinel').exists()
    leftovers=[x.name for pattern in ('.fm-custom-check.*','.fm-check-output.*') for x in state.glob(pattern)]
    assert not leftovers and not (state/'.watch.lock').exists()
    report('Fallback timeout: TERM after direct check returns',result='pass',registration=registration.stdout.strip(),watcher_before=before,watcher_exit=rc,term_to_exit_seconds=elapsed,recorded_descendant_pid=child,descendant_after=child_state or 'absent',sentinel_exists=False,private_files_left=leftovers,singleton_lock_exists=False)

    for existing in (False,True):
        name='held-marker-existing' if existing else 'held-marker-new'
        p=home(name); state=p/'state'; w=start(p,name)
        marker=state/'.watcher-down'
        if existing:
            r=run(p,'. "$1"; fm_recovery_marker_publish "$2" downtime',marker)
            assert r.returncode==0, r.stderr
        before_token=read(marker)
        holder=lock_holder(p,state/'.watcher-down.lock',name+'-holder')
        rc,elapsed=stop(w)
        err=read(EVIDENCE/(name+'.stderr.log'))
        assert rc!=0 and elapsed<20 and 'within 5s' in err and f'held by pid {holder.pid}' in err
        assert holder.poll() is None and read(state/'.watcher-down.lock/pid')==str(holder.pid)
        assert read(state/'.watch.lock/pid')==str(w.pid)
        assert read(marker)==before_token
        report(name,result='pass',watcher_pid=w.pid,watcher_exit=rc,term_to_exit_seconds=elapsed,diagnostic=err,holder_process=ps(holder.pid),retained_watcher_lock_pid=read(state/'.watch.lock/pid'),marker_before=before_token,marker_after=read(marker))
        stop(holder)

    p=home('unwritable-state'); state=p/'state'; w=start(p,'unwritable-state')
    wait_until(lambda: not (state/'.watcher-down.lock').exists())
    state.chmod(0o555)
    t=time.monotonic(); r=run(p,'. "$1"; if fm_lock_owner_dir "$2"; then exit 10; fi; if fm_lock_try_acquire "$2"; then rc=0; else rc=$?; fi; echo acquisition_rc=$rc; exit "$rc"',state/'.resource.lock')
    primitive_time=round(time.monotonic()-t,3)
    assert r.returncode==1, (r.returncode,r.stdout,r.stderr)
    rc,elapsed=stop(w)
    err=read(EVIDENCE/'unwritable-state.stderr.log')
    assert rc!=0 and elapsed<20 and 'within 5s' in err and 'retaining stale lock evidence' in err
    assert read(state/'.watch.lock/pid')==str(w.pid)
    report('Resource fault: genuine unwritable state',result='pass',uid=os.getuid(),state_mode='0555',primitive_output=r.stdout.strip(),primitive_elapsed_seconds=primitive_time,watcher_exit=rc,term_to_exit_seconds=elapsed,diagnostic=err,retained_watcher_lock_pid=read(state/'.watch.lock/pid'))
    state.chmod(0o755)

    p=home('ordinary-publish'); lock=p/'state/.watcher-down.lock'; marker=p/'state/.watcher-down'
    holder=lock_holder(p,lock,'ordinary-publish-holder')
    t=time.monotonic()
    publisher=spawn(p,['bash','-c','. "$1"; fm_recovery_marker_publish "$2" downtime; echo publish_rc=$?','_',LIB,marker],'ordinary-publish',FM_RECOVERY_MARKER_LOCK_TIMEOUT='1',FM_WATCHER_SHUTDOWN_LOCK_SECS='1')
    time.sleep(6)
    blocked=publisher.poll() is None and not marker.exists()
    assert blocked, 'ordinary marker publication did not keep blocking'
    stop(holder); rc=publisher.wait(timeout=10)
    assert rc==0 and read(marker).startswith('pending:downtime:')
    report('Ordinary publication ignores ambient timeout overrides',result='pass',ambient_values={'FM_RECOVERY_MARKER_LOCK_TIMEOUT':'1','FM_WATCHER_SHUTDOWN_LOCK_SECS':'1'},blocked_after_seconds=6,publication_exit=rc,marker=read(marker),elapsed_seconds=round(time.monotonic()-t,3))

    p=home('abandoned-stealer'); state=p/'state'; lock=state/'.watch.lock'
    first=lock_holder(p,lock,'abandoned-primary')
    first.kill(); first.wait()
    script='''. "$1"
set -T
trap 'if [ "$BASH_COMMAND" = "rc=1" ] && [ "${lockdir:-}" = "$STATE/.watch.lock" ] && [ ! -e "$STATE/.watch.lock" ] && [ -e "$STATE/.watch.lock.steal" ]; then printf "%s\\n" "${BASHPID:-$$}" > "$STATE/steal-gap"; kill -STOP "${BASHPID:-$$}"; fi' DEBUG
fm_lock_try_acquire "$STATE/.watch.lock"
'''
    stealer=spawn(p,['bash','-c',script,'_',LIB],'abandoned-stealer')
    wait_until(lambda: (state/'steal-gap').exists())
    at_gap=ps(stealer.pid)
    assert not lock.exists() and (state/'.watch.lock.steal').exists()
    abandoned_pid=read(state/'.watch.lock.steal/pid')
    assert abandoned_pid==str(stealer.pid)
    stealer.kill(); stealer.wait()
    r=run(p,'. "$1"; fm_lock_try_acquire "$2" || exit 12; echo acquired_pid=$(cat "$2/pid"); echo recovered_pid=$FM_LOCK_RECOVERED_PID; fm_lock_release "$2"',lock)
    assert r.returncode==0, r.stderr
    assert not (state/'.watch.lock.steal').exists()
    # A real watcher must also be able to start after that abandoned gap.
    w=start(p,'after-abandoned-stealer')
    rc,elapsed=stop(w)
    report('Stealer dies after removing primary lock; next acquirer and watcher start',result='pass',stopped_stealer=at_gap,primary_absent_at_crash=True,abandoned_steal_pid=abandoned_pid,next_acquirer_output=r.stdout.strip(),next_acquirer_exit=r.returncode,steal_lock_reclaimed=True,successor_watcher_pid=w.pid,successor_exit_after_term=rc,successor_term_to_exit_seconds=elapsed)

    p=home('self-held'); marker=p/'state/.watcher-down'
    r=run(p,'. "$1"; fm_lock_try_acquire "$2.lock" || exit 11; FM_RECOVERY_MARKER_LOCK_TIMEOUT=5; fm_recovery_marker_publish "$2" downtime || exit 12; echo marker=$(cat "$2"); echo reacquired_and_released',marker)
    assert r.returncode==0 and 'reacquired_and_released' in r.stdout, r.stderr
    report('Same process reclaims interrupted marker lock',result='pass',exit=r.returncode,output=r.stdout.strip())
finally:
    for p in procs:
        if p.poll() is None:
            p.kill()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: pass
    for f in handles: f.close()
    for p in LAB.glob('*/state'):
        p.chmod(0o755)
