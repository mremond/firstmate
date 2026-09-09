#!/usr/bin/env python3
"""Process-level checks. Execute from the assigned worktree; no global writes."""
import os, pathlib, subprocess as sp, signal, time, json, shutil, sys
ROOT=pathlib.Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22Z7YQYD4K70MWCSC6FV3P4')
EVID=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M22Z7YQYD4K70MWCSC6FV3P4')
assert pathlib.Path.cwd()==ROOT
WORK=ROOT/'.test-phase'
TMP=WORK/'tmp'; TMP.mkdir(parents=True,exist_ok=True)
BASE_ENV={k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'TMUX', 'HERDR_', 'ORCA_'))}
BASE_ENV.update(TMPDIR=str(TMP), FM_TEST_SKIP_ORPHAN_REAP='1')
PROCS=[]; HANDLES=[]; EVENTS=[]
def log(s):
    print(s,flush=True); EVENTS.append(s)
def wait_until(f,seconds=10):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if f(): return
        time.sleep(.025)
    raise AssertionError('readiness deadline exceeded')
def text(p):
    try: return p.read_text()
    except FileNotFoundError: return ''
def env_for(home):
    e=BASE_ENV.copy(); e.update(FM_HOME=str(home),FM_POLL='0.1',FM_SIGNAL_GRACE='0', FM_CHECK_INTERVAL='999999',FM_HEARTBEAT='999999')
    return e
def home_for(name):
    h=WORK/name
    for sub in ('state','config','data'): (h/sub).mkdir(parents=True,exist_ok=True)
    (h/'config/backend').write_text('tmux\n')
    (h/'state/home-summary.json').write_text('{}\n')
    return h

def start(name,cmd,env):
    out=open(EVID/(name+'.out'),'w'); err=open(EVID/(name+'.err'),'w'); HANDLES.extend((out,err))
    p=sp.Popen(cmd,cwd=ROOT,env=env,stdout=out,stderr=err,start_new_session=True)
    PROCS.append(p); log(f'START {name}: pid={p.pid} command={cmd}')
    return p

def snap(pid):
    return sp.run(['ps','-p',str(pid),'-o','pid=,ppid=,pgid=,stat=,wchan=,args='],text=True,capture_output=True).stdout.strip() or '(pid gone)'
def stop(p,name,ceiling=20):
    log(f'BEFORE TERM: {snap(p.pid)}')
    t=time.monotonic(); p.send_signal(signal.SIGTERM)
    try: rc=p.wait(timeout=ceiling)
    except sp.TimeoutExpired:
        log(f'REMAINED LIVE after {ceiling}s: {snap(p.pid)}'); raise
    elapsed=time.monotonic()-t
    log(f'AFTER TERM {name}: exit={rc}; elapsed={elapsed:.3f}s; {snap(p.pid)}')
    assert rc!=0
    err=text(EVID/(name+'.err')); log(f'STDERR {name}: {err.strip() or "(empty)"}')
    return elapsed,err

def watch(name,home,runtime=ROOT):
    p=start(name,[str(runtime/'bin/fm-watch.sh')],env_for(home))
    state=home/'state'
    wait_until(lambda: text(state/'.watch.lock/pid').strip()==str(p.pid) and (state/'.last-watcher-beat').exists())
    # Let initial marker operations settle before inducing the shutdown fault.
    wait_until(lambda: not os.path.lexists(state/'.watcher-down.lock'))
    assert p.poll() is None
    return p

def primitive(home,code,*args,runtime=ROOT,timeout=8):
    return sp.run(['bash','-eu','-c','. "$1"; shift\n'+code,'_',str(runtime/'bin/fm-wake-lib.sh'),*map(str,args)],cwd=ROOT,env=env_for(home),text=True,capture_output=True,timeout=timeout)

def normal():
    h=home_for('normal'); p=watch('normal',h); elapsed,err=stop(p,'normal')
    assert elapsed<20 and not os.path.lexists(h/'state/.watch.lock')
    marker=text(h/'state/.watcher-down'); assert marker
    log('PERSISTED normal recovery marker:\n'+marker)
    assert not err.strip(); log('PASS ordinary signal shutdown publishes downtime and releases singleton')

def held():
    h=home_for('held'); s=h/'state'; p=watch('held',h)
    holder=start('holder',['bash','-eu','-c','. "$1"; fm_lock_acquire_wait "$2"; printf "ready\\n" > "$3"; sleep 300','_',str(ROOT/'bin/fm-wake-lib.sh'),str(s/'.watcher-down.lock'),str(h/'ready')],env_for(h))
    wait_until(lambda:(h/'ready').exists()); owner=text(s/'.watcher-down.lock/pid').strip(); assert owner==str(holder.pid)
    elapsed,err=stop(p,'held'); assert elapsed<20 and 'within 5s' in err and f'pid {holder.pid}' in err
    assert holder.poll() is None and text(s/'.watcher-down.lock/pid').strip()==owner
    assert text(s/'.watch.lock/pid').strip()==str(p.pid)
    log(f'PRESERVED marker holder={owner}, holder state={snap(holder.pid)}, stale watcher owner={text(s/".watch.lock/pid").strip()}')
    os.killpg(holder.pid,signal.SIGKILL); holder.wait()
    # A real subsequent watcher consumes the stale locks and surfaces recovery.
    successor=start('held-restart',[str(ROOT/'bin/fm-watch.sh')],env_for(h))
    rc=successor.wait(timeout=15); out=text(EVID/'held-restart.out')
    log(f'RESTART exit={rc}; stdout={out.strip()}; stderr={text(EVID/"held-restart.err").strip()}')
    assert rc==0 and 'rearm-resurface' in out and not os.path.lexists(s/'.watch.lock')
    log('PASS held lock bounds shutdown, leaves foreign holder intact, and allows recovery on next start')

def resource(name='resource',runtime=ROOT,expect_mutant=False):
    assert os.getuid()!=0, 'root bypasses resource fault'
    h=home_for(name); s=h/'state'; p=watch(name,h,runtime)
    s.chmod(0o555)
    try:
        probe=primitive(h,'if fm_lock_owner_dir "$1"; then exit 10; else printf "owner-directory creation failed\\n"; fi',s/'.watcher-down.lock',runtime=runtime)
        assert probe.returncode==0
        log(f'FAULT uid={os.getuid()}; state_mode={oct(s.stat().st_mode & 0o777)}; marker absent={not os.path.lexists(s/".watcher-down.lock")}; {probe.stdout.strip()}')
        t=time.monotonic()
        acq=start(name+'-primitive',['bash','-eu','-c','. "$1"; if fm_lock_try_acquire "$2"; then rc=0; else rc=$?; fi; printf "acquire returned %s\\n" "$rc"; exit "$rc"','_',str(runtime/'bin/fm-wake-lib.sh'),str(s/'.resource.lock')],env_for(h))
        if expect_mutant:
            try: acq.wait(timeout=6); raise AssertionError('resource mutant unexpectedly returned')
            except sp.TimeoutExpired: log('EXPECTED RED: resource-error mutant primitive still running after 6s'); os.killpg(acq.pid,signal.SIGKILL); acq.wait()
            try: stop(p,name,20); raise AssertionError('resource mutant watcher unexpectedly stopped')
            except sp.TimeoutExpired: log('EXPECTED RED: resource-error mutant watcher exceeds unchanged 20s ceiling'); os.killpg(p.pid,signal.SIGKILL); p.wait()
            return
        rc=acq.wait(timeout=6); elapsed=time.monotonic()-t
        log(f'PRIMITIVE returned rc={rc} in {elapsed:.3f}s; stdout={text(EVID/(name+"-primitive.out")).strip()}')
        assert rc!=0 and 'acquire returned' in text(EVID/(name+'-primitive.out'))
        elapsed,err=stop(p,name)
        assert elapsed<20 and 'within 5s' in err and 'stopping and retaining stale lock evidence' in err
        assert text(s/'.watch.lock/pid').strip()==str(p.pid)
        log('PASS resource failure returns from acquisition and signalled watcher reaches reporting deadline')
    finally: s.chmod(0o755)

def abandoned():
    h=home_for('abandoned'); s=h/'state'; lock=s/'.watch.lock'
    # Seed a genuine owner then let it exit without releasing.
    seed=primitive(h,'fm_lock_try_acquire "$1"; printf "seed owner=%s\\n" "$$"',lock)
    assert seed.returncode==0; log(seed.stdout.strip()); assert lock.is_symlink()
    shim=h/'intercept'; shim.mkdir(); rm=shim/'rm'
    rm.write_text('''#!/bin/bash
/bin/rm "$@"
rc=$?
for arg in "$@"; do
  if [ "$arg" = "$INTERRUPT_LOCK" ] && [ ! -e "$INTERRUPT_READY" ]; then
    printf '%s\\n' "$PPID" > "$INTERRUPT_READY"
    kill -STOP "$PPID"
    sleep 300
  fi
done
exit "$rc"
'''); rm.chmod(0o700)
    e=env_for(h); e.update(PATH=str(shim)+':'+e['PATH'],INTERRUPT_LOCK=str(lock),INTERRUPT_READY=str(h/'removed'))
    stealer=start('abandoned-stealer',['bash','-eu','-c','. "$1"; fm_lock_try_acquire "$2"','_',str(ROOT/'bin/fm-wake-lib.sh'),str(lock)],e)
    wait_until(lambda:(h/'removed').exists()); assert not os.path.lexists(lock)
    steal_owner=text(s/'.watch.lock.steal/pid').strip(); assert steal_owner==str(stealer.pid)
    log(f'CRASH POINT: primary absent; .steal owner={steal_owner}; {snap(stealer.pid)}')
    os.killpg(stealer.pid,signal.SIGKILL); stealer.wait(); log('Killed stealer after primary removal and before replacement')
    # One next real acquirer must reclaim .steal, not reject absent primary.
    acq=primitive(h,'fm_lock_try_acquire "$1"; printf "acquired pid=%s stored=%s\\n" "$$" "$(cat "$1/pid")"; fm_lock_release "$1"',lock,timeout=12)
    log(f'NEXT ACQUIRER exit={acq.returncode}; stdout={acq.stdout.strip()}; stderr={acq.stderr.strip()}')
    assert acq.returncode==0 and 'acquired pid=' in acq.stdout and not os.path.lexists(s/'.watch.lock.steal')
    successor=start('abandoned-restart',[str(ROOT/'bin/fm-watch.sh')],env_for(h))
    rc=successor.wait(timeout=15); out=text(EVID/'abandoned-restart.out')
    log(f'NEXT WATCHER exit={rc}; stdout={out.strip()}; stderr={text(EVID/"abandoned-restart.err").strip()}')
    assert rc==0 and 'rearm-resurface' in out
    log('PASS abandoned steal recovery permits next acquisition and watcher startup')

def custom_fallback():
    h=home_for('custom-fallback'); s=h/'state'
    custom=s/'custom.check.sh'
    custom.write_text('''#!/bin/bash
perl -e '$SIG{TERM}="IGNORE"; open my $f, ">", $ENV{FM_TEST_READY} or die $!; print {$f} "ready\\n"; close $f; sleep 4; open my $s, ">", $ENV{FM_TEST_SENTINEL} or die $!; print {$s} "late\\n"; close $s; sleep 1' &
printf '%s\\n' "$!" > "$FM_TEST_CHILD"
while [ ! -s "$FM_TEST_READY" ]; do sleep 0.01; done
: > "$FM_TEST_DIRECT"
''');custom.chmod(0o700)
    e=env_for(h);e.update(FM_CHECK_FORCE_FALLBACK='1',FM_CHECK_TIMEOUT='10',FM_TEST_READY=str(h/'ready'),FM_TEST_SENTINEL=str(h/'sentinel'),FM_TEST_CHILD=str(h/'child'),FM_TEST_DIRECT=str(h/'direct'))
    reg=sp.run([str(ROOT/'bin/fm-check-register.sh'),'custom'],env=e,cwd=ROOT,text=True,capture_output=True)
    log(f'REGISTER custom exit={reg.returncode}; output={reg.stdout.strip()} {reg.stderr.strip()}');assert reg.returncode==0
    p=start('custom-fallback',[str(ROOT/'bin/fm-watch.sh')],e)
    wait_until(lambda:(h/'direct').exists() and (s/'.last-check').exists(),12)
    child=int(text(h/'child')); log(f'RETURNED CHECK: watcher={snap(p.pid)}; recorded descendant={snap(child)}')
    elapsed,err=stop(p,'custom-fallback')
    stat=sp.run(['ps','-p',str(child),'-o','stat='],text=True,capture_output=True).stdout.strip()
    assert not stat or stat.startswith('Z')
    assert not (h/'sentinel').exists() and not list(s.glob('.fm-custom-check.*'))
    log(f'PASS real fallback custom check returns, watcher exits in {elapsed:.3f}s, child state={stat or "gone"}, no sentinel or snapshot remains')

def targeted():
    specs=[('fm-test-fixtures.test.sh','test_touch_epoch_preserves_repeated_dst_hour',['test_is_live_non_zombie_separates_gone_from_unreadable']),('fm-watcher-lock.test.sh','test_singleton_start',['test_shutdown_is_bounded_when_marker_lock_is_held','test_lock_resource_failure_returns || exit $?','test_shutdown_is_bounded_when_state_is_unwritable || exit $?','test_lock_steals_dead_pid_lock','test_lock_live_steal_mutex_is_not_reclaimed','test_lock_empty_pid_uses_minimum_grace','test_lock_paused_mid_acquire_claim_fails_during_steal']),('fm-pr-check-security.test.sh','test_parser_matrix',['set -e','test_custom_snapshot_cleanup_on_signal','test_returned_custom_check_descendants_are_drained']),('fm-wake-queue.test.sh','test_atomic_status_enqueue',['test_self_held_lock_reclaims_instead_of_deadlocking'])]
    for file,first,functions in specs[:3]:
        source=(ROOT/'tests'/file).read_text(); prefix=source.split('\n'+first+'\n')[0]
        assert prefix!=source
        runner=ROOT/'tests'/('.phase-'+file)
        runner.write_text(prefix+'\n'+'\n'.join(functions)+'\n')
        try:
            p=start('targeted-'+file,['bash',str(runner)],BASE_ENV)
            rc=p.wait(timeout=150); out=text(EVID/('targeted-'+file+'.out'));err=text(EVID/('targeted-'+file+'.err'))
            log(f'TARGETED {file}: selectors={functions}; exit={rc}\n{out}{err}');assert rc==0
        finally:runner.unlink(missing_ok=True)

try:
    mode=sys.argv[1]
    if mode=='live': normal();held();resource();abandoned();custom_fallback()
    elif mode=='targeted':targeted()
    elif mode=='resource-mutation':
        runtime=WORK/'mutant-resource'; shutil.copytree(ROOT/'bin',runtime/'bin',dirs_exist_ok=True)
        lib=runtime/'bin/fm-wake-lib.sh'; src=lib.read_text();src=src.replace('ownerdir=$(fm_lock_owner_dir "$lockdir") || return 2','ownerdir=$(fm_lock_owner_dir "$lockdir") || return 1');src=src.replace('  [ "$rc" -eq 1 ] || return 1\n','')
        lib.write_text(src);resource('resource-mutant',runtime,True)
    else:raise ValueError(mode)
finally:
    for p in PROCS:
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        p.wait()
    for f in HANDLES:f.close()
    (EVID/(sys.argv[1]+'-transcript.txt')).write_text('\n'.join(EVENTS)+'\n')
