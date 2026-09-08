#!/usr/bin/env python3
"""Drive the real registered-command runner, using OS processes and signals.
No product functions or OS tools are mocked. The registered shell command is
our controlled workload: a TERM handler and a child that logs ongoing work.
"""
import os, sys, time, signal, subprocess, json, pathlib, traceback, shlex
ROOT = pathlib.Path.cwd()
SCRATCH = ROOT / '.procevent-validation'
EVIDENCE = pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M20JG8RNK8A0BPJA70D7QNX2')
MODE = sys.argv[1] if len(sys.argv)>1 else 'initial'
TRANSCRIPT = (EVIDENCE / ('live-cli-transcript.log' if MODE=='initial' else MODE+'-transcript.log')).open('w')
RESULTS = []
ENVS = []
GROUPS = []
CHILDREN = []
T0 = time.monotonic()
def log(s):
    line = f'[{time.monotonic()-T0:8.3f}s] {s}'
    print(line, flush=True); TRANSCRIPT.write(line+'\n'); TRANSCRIPT.flush()
def alive(pid):
    try: os.kill(pid, 0); return True
    except ProcessLookupError: return False
def eventually(fn, seconds=12):
    stop=time.monotonic()+seconds
    while time.monotonic()<stop:
        if fn(): return True
        time.sleep(.05)
    return bool(fn())
def nonempty(p): return p.exists() and p.stat().st_size > 0
def check(ok, message):
    log(('PASS ' if ok else 'FAIL ') + message)
    if not ok: raise AssertionError(message)
def snapshot(label, pid):
    p=subprocess.run(['/bin/ps','-axo','pid=,ppid=,pgid=,stat=,command='],capture_output=True,text=True)
    rows=[]
    for line in p.stdout.splitlines():
        cols=line.split(None,4)
        if len(cols)==5 and (cols[2]==str(pid) or ('_owner-watchdog' in cols[4] and ' '+str(pid)+' ' in cols[4])):
            rows.append(line)
    log(label+'\nPID PPID PGID STAT COMMAND\n'+'\n'.join(rows or ['(no group members or guard)']))
    return rows
WORKLOAD=SCRATCH/'poll-command.sh'
WORKLOAD.write_text('''#!/usr/bin/env bash
marker=$1
mode=$2
trap 'printf "TERM\\n" >> "$marker.signals"' TERM INT HUP
[ "$mode" = resistant ] || trap - TERM INT HUP
printf '%s\\n' "$$" > "$marker.child"
if [ "$mode" = healthy ]; then
  sleep 120 &
  printf '%s\\n' "$!" > "$marker.descendant"
fi
while [ "$SECONDS" -lt 120 ]; do
  printf 'tick\\n' >> "$marker.ticks"
  sleep 0.1 &
  wait $!
done
''')
WORKLOAD.chmod(0o755)
def make(version, name, mode='resistant', short=False):
    code=ROOT if version=='target' else SCRATCH/'baseline'
    home=SCRATCH/(version+'-'+name); (home/'state').mkdir(parents=True)
    claims=home/'claims'
    env=os.environ.copy()
    for k in ('FM_STATE_OVERRIDE','FM_ROOT_OVERRIDE','FM_PROCEVENT_IN_RUNNER','FM_PROCEVENT_RUNNER_GROUP','FM_PROC_ROOT_OVERRIDE','FM_TASK_ID'):
        env.pop(k,None)
    env.update(FM_HOME=str(home), FM_PROCEVENT_CLAIM_ROOT=str(claims),
               FM_PROCEVENT_OWNER_LEASE_SECONDS='2' if short else '600',
               FM_PROCEVENT_OWNER_CHECK_SECONDS='1', TMPDIR=str(SCRATCH/'tmp'))
    ctx=dict(code=code,home=home,env=env,id=name,marker=home/'poll',claims=claims)
    ENVS.append(ctx)
    command(ctx,'register','lavish',name,'--',str(WORKLOAD),str(ctx['marker']),mode)
    return ctx

def command(c,*args,allow_fail=False):
    argv=[str(c['code']/'bin/fm-procevent.sh'),*args]
    log('$ FM_HOME='+str(c['home'])+' '+shlex.join(argv))
    t=time.monotonic()
    p=subprocess.run(argv,env=c['env'],capture_output=True,text=True,timeout=25)
    log(f'exit={p.returncode} elapsed={time.monotonic()-t:.3f}s stdout={p.stdout.strip()!r} stderr={p.stderr.strip()!r}')
    if p.returncode and not allow_fail: raise RuntimeError(p.stderr)
    return p

def start(c, mode='attached'):
    path=c['home']/'start.log'; f=path.open('w'); c['start_log']=path
    if mode=='detached': command(c,'reconcile'); proc=None
    elif mode=='zombie':
        c['release']=c['home']/'reap'
        # Same isolated process-group launch as the product's start, except the
        # parent deliberately withholds waitpid so a real Darwin zombie exists.
        program='''my $release=shift @ARGV; defined(my $pid=fork) or exit 125;
if ($pid==0) { setpgrp(0,0) or exit 125; $ENV{FM_PROCEVENT_RUNNER_GROUP}=$$; exec @ARGV; exit 125; }
my $deadline=time+120; while (!-e $release && time<$deadline) { select undef,undef,undef,.05; }
waitpid($pid,0); exit 0;'''
        proc=subprocess.Popen(['/usr/bin/perl','-e',program,str(c['release']),str(c['code']/'bin/fm-procevent.sh'),'_start',c['id']],env=c['env'],stdout=f,stderr=subprocess.STDOUT)
    else:
        proc=subprocess.Popen([str(c['code']/'bin/fm-procevent.sh'),'start',c['id']],env=c['env'],stdout=f,stderr=subprocess.STDOUT)
    f.close(); c['proc']=proc
    if proc: CHILDREN.append(proc)
    runner=c['home']/'state/procevent'/(c['id']+'.runner')
    if not eventually(lambda: nonempty(runner) and nonempty(pathlib.Path(str(c['marker'])+'.child'))):
        raise RuntimeError('start failed: '+path.read_text())
    c['pid']=int(runner.read_text()); c['child']=int(pathlib.Path(str(c['marker'])+'.child').read_text())
    GROUPS.append(c['pid']); snapshot('running '+c['id'],c['pid'])
    return c['pid']
def save_state(c,label):
    out={}
    for p in (c['home']/'state/procevent').glob('*'):
        if p.is_file() and not p.name.startswith('.'):
            out[p.name]=p.read_text(errors='replace')[:3000]
    claim=c['claims']/(c['id']+'.claim')
    out['claim']=claim.read_text() if claim.exists() else None
    (EVIDENCE/(label+'-state.json')).write_text(json.dumps(out,indent=2))

def healthy(version):
    c=make(version,'healthy','healthy'); pid=start(c)
    t=time.monotonic(); command(c,'retire',c['id']); elapsed=time.monotonic()-t
    status=c['proc'].wait(timeout=15)
    log(f'{version} healthy public start exit={status}; TERM=143, KILL=137; retirement={elapsed:.3f}s')
    check(not alive(-pid),'healthy retirement leaves no process-group members')
    check(status==(143 if version=='target' else 137), version+' healthy runner has expected observed signal status')
    save_state(c,version+'-healthy')
    return dict(start_exit=status,retire_seconds=round(elapsed,3),group_gone=True)

def guard(version):
    c=make(version,'guard-expiry' if MODE=='initial' else 'guard-clock',short=True); pid=start(c,'detached')
    lease=c['home']/'state/procevent/.owner-lease'; last=float(lease.read_text())
    t=time.monotonic(); signals=pathlib.Path(str(c['marker'])+'.signals')
    check(eventually(lambda: nonempty(signals),15),'expired owner guard sends TERM to registered blocking command')
    term_after=time.monotonic()-t
    snapshot('after guard TERM',pid)
    if version=='base':
        check(eventually(lambda: not alive(pid),8),'base guard loses the leader to its own TERM')
        before=pathlib.Path(str(c['marker'])+'.ticks').read_text().count('\n')
        time.sleep(4)
        after=pathlib.Path(str(c['marker'])+'.ticks').read_text().count('\n')
        snapshot('base abandoned survivor after TERM grace',pid)
        check(alive(c['child']) and after>before,'base guard abandons live child with ongoing work after its own TERM')
        result=dict(term_after_seconds=round(term_after,3),leader_gone=True,child_survives=True,ticks_before=before,ticks_after=after)
        os.killpg(pid,signal.SIGKILL)
    else:
        check(eventually(lambda: not alive(-pid),12),'target guard escalates and stops all group members')
        elapsed=time.monotonic()-t
        age=time.clock_gettime(time.CLOCK_MONOTONIC)-last
        check(0<age<15,'short lease/check guard ends workload within observed lease + checks + stop grace allowance')
        before=pathlib.Path(str(c['marker'])+'.ticks').read_text().count('\n'); time.sleep(.5)
        after=pathlib.Path(str(c['marker'])+'.ticks').read_text().count('\n')
        check(before==after,'work log ceases after guard cleanup')
        snapshot('target group reaped',pid)
        result=dict(term_after_seconds=round(term_after,3),group_gone=True,after_ready_seconds=round(elapsed,3),since_last_lease_seconds=round(age,3))
    save_state(c,version+'-guard')
    return result

def retire_transition(mode):
    c=make('target','retire-'+mode); pid=start(c,mode)
    f=(c['home']/'retire.log').open('w')
    stop=subprocess.Popen([str(c['code']/'bin/fm-procevent.sh'),'retire',c['id']],env=c['env'],stdout=f,stderr=subprocess.STDOUT); CHILDREN.append(stop); f.close()
    if mode=='zombie':
        def transitioned():
            return subprocess.run(['/bin/ps','-o','stat=','-p',str(pid)],capture_output=True,text=True).stdout.strip().startswith('Z')
    else: transitioned=lambda: not alive(pid)
    check(eventually(transitioned,8),'TERM leaves a real '+mode+' runner leader')
    check(alive(c['child']),'blocking child survives leader transition and needs escalation')
    snapshot('TERM transition '+mode,pid)
    check(eventually(lambda: not alive(c['child']),8),'forced escalation reaps child after '+mode+' transition')
    if mode=='zombie': c['release'].touch()
    status=stop.wait(timeout=15)
    check(status==0,'retire succeeds after '+mode+' transition: '+(c['home']/'retire.log').read_text().strip())
    c['proc'].wait(timeout=15)
    check(eventually(lambda:not alive(-pid),5),'no remaining group after '+mode+' escalation')
    save_state(c,'target-'+mode)
    return dict(retire_exit=status,child_survived_term=True,group_gone=True)

def cleanup_path(which):
    c=make('target','cleanup-'+which,'healthy'); pid=start(c)
    if which=='reconcile': (c['home']/'state/procevent'/(c['id']+'.source')).unlink()
    out=command(c,which)
    status=c['proc'].wait(timeout=10)
    check(status==143,which+' healthy cleanup ends with TERM, not KILL')
    check(not alive(-pid),which+' leaves no remaining group')
    return dict(start_exit=status,stdout=out.stdout.strip())

def stale_identity():
    c=make('target','stale-identity'); pid=start(c)
    claim=c['claims']/(c['id']+'.claim'); lines=claim.read_text().splitlines()
    # Claim identity is persisted public state, deliberately made stale while
    # the real leader remains alive. No ps or identity implementation is mocked.
    original=claim.read_text(); lines[3]='known-old-generation'; claim.write_text('\n'.join(lines)+'\n')
    p=command(c,'retire',c['id'],allow_fail=True)
    check(p.returncode!=0 and 'cannot confirm runner identity' in p.stderr,'stale readable identity refuses first signal')
    check(alive(pid) and alive(c['child']),'stale generation refusal preserves live leader and child')
    check(not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'no TERM delivered through stale claim')
    save_state(c,'target-stale-refusal'); claim.write_text(original); command(c,'retire',c['id'])
    c['proc'].wait(timeout=10)
    return dict(retire_exit=p.returncode,term_received=False,leader_preserved=True)

def crashed():
    c=make('target','crashed-leader',short=True); pid=start(c,'detached')
    os.kill(pid,signal.SIGKILL)
    check(eventually(lambda:not alive(pid),5),'external KILL removes only runner leader')
    check(alive(c['child']),'externally killed leader leaves blocking child')
    time.sleep(5)
    check(alive(c['child']),'guard refuses externally created leaderless group after lease expiry')
    outputs={}
    for action in ('retire','reconcile','sweep-home'):
        p=command(c,action,*([c['id']] if action=='retire' else []),allow_fail=True)
        outputs[action]=dict(exit=p.returncode,stdout=p.stdout.strip(),stderr=p.stderr.strip())
        check(alive(c['child']),'external-crash group is not signalled by '+action)
    check(not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'all callers preserve external-crash refusal without TERM')
    source=c['home']/'state/procevent'/(c['id']+'.source')
    check(source.exists() and (c['claims']/(c['id']+'.claim')).exists(),'crashed source and claim remain, blocking replacement')
    check(not list((c['home']/'state').glob('procevent-inbox/*.result')),'crashed source produces no captured result')
    snapshot('permanent refusal residue',pid); save_state(c,'target-crash-residue')
    os.killpg(pid,signal.SIGKILL)
    return outputs

def home_scope():
    expired=make('target','scope-expired',short=True); ep=start(expired,'detached')
    kept=make('target','scope-live',short=True); kp=start(kept,'attached')
    check(eventually(lambda:not alive(-ep),15),'expired home group is reaped')
    check(alive(kp) and alive(kept['child']),'same workload in an attached live home remains running')
    check(not nonempty(pathlib.Path(str(kept['marker'])+'.signals')),'live home receives no stop signal')
    command(kept,'retire',kept['id']); kept['proc'].wait(timeout=10)
    return dict(expired_group_gone=True,live_home_unsignalled=True)

def private_tools(c):
    d=c['home']/'tools'; d.mkdir()
    for parent in ('/opt/homebrew/bin','/usr/bin','/bin','/usr/sbin','/sbin'):
        for p in pathlib.Path(parent).iterdir():
            dest=d/p.name
            if not dest.exists() and not dest.is_symlink() and p.is_file() and os.access(p,os.X_OK): dest.symlink_to(p)
    return d

def identity(c,pid,env=None):
    p=subprocess.run(['bash','-c','. "$1/bin/fm-wake-lib.sh"; fm_pid_identity "$2"','_',str(ROOT),str(pid)],env=env or c['env'],capture_output=True,text=True)
    log(f'identity read pid={pid} exit={p.returncode} value={p.stdout.strip()!r}')
    return p

def unavailable_identity():
    c=make('target','ps-unavailable'); pid=start(c)
    d=private_tools(c); env=c['env'].copy(); env['PATH']=str(d)
    os.kill(pid,signal.SIGSTOP)
    link=d/'ps'; saved=os.readlink(link); link.unlink()
    check(identity(c,pid,env).returncode!=0,'live identity cannot be read when local ps executable is unavailable')
    original_env=c['env']; c['env']=env
    p=command(c,'retire',c['id'],allow_fail=True)
    check(p.returncode!=0 and alive(c['child']),'unproved stop refuses unreadable identity')
    check(not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'unproved unreadable identity delivers no TERM')
    link.symlink_to(saved)
    log('Restored real ps for initial ownership proof; the runner remains stopped and live')
    f=(c['home']/'retire-late.log').open('w')
    stop=subprocess.Popen([str(ROOT/'bin/fm-procevent.sh'),'retire',c['id']],env=env,stdout=f,stderr=subprocess.STDOUT); CHILDREN.append(stop); f.close()
    check(eventually(lambda:nonempty(pathlib.Path(str(c['marker'])+'.signals')),5),'proved first TERM reached the blocking child')
    link.unlink()
    check(identity(c,pid,env).returncode!=0,'ps becomes genuinely unavailable during proved escalation')
    check(alive(pid),'unreadable leader remains live during escalation')
    status=stop.wait(timeout=15)
    log('late-identity stop output: '+(c['home']/'retire-late.log').read_text().strip())
    check(status==0 and not alive(-pid),'proved stop completes KILL despite loss of ps')
    c['env']=original_env; c['proc'].wait(timeout=10)
    return dict(unproved_retire_exit=p.returncode,proved_retire_exit=status,group_gone=True,ps_is_real_missing_executable=True)

def nonleader_identity():
    c=make('target','nonleader'); pid=start(c)
    claim=c['claims']/(c['id']+'.claim'); original=claim.read_text(); rows=original.splitlines()
    p=identity(c,c['child']); check(p.returncode==0,'actual nonleader process identity is readable')
    rows[1]=str(c['child']); rows[3]=p.stdout.strip(); claim.write_text('\n'.join(rows)+'\n')
    observed=subprocess.run(['/bin/ps','-o','pid=,pgid=','-p',str(c['child'])],capture_output=True,text=True).stdout.strip()
    log('real nonleader PID PGID: '+observed)
    out=command(c,'retire',c['id'],allow_fail=True)
    check(out.returncode!=0 and alive(c['child']),'first signal refuses readable matching identity that does not lead its group')
    check(not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'nonleader refusal delivered no TERM')
    save_state(c,'target-nonleader-refusal'); claim.write_text(original)
    command(c,'retire',c['id']); c['proc'].wait(timeout=10)
    return dict(retire_exit=out.returncode,term_received=False,nonleader_pid_pgid=observed)

def single_lease_miss():
    c=make('target','lease-debounce',short=True)
    c['env']['FM_PROCEVENT_OWNER_CHECK_SECONDS']='2'
    pid=start(c,'detached')
    lease=c['home']/'state/procevent/.owner-lease'
    # Locate the real guard's sleeping child. After its first sleep starts,
    # remove only the private lease for one complete guard evaluation, then
    # restore it during the next sleep. This uses real process state, no shim.
    def guard_sleep():
        rows=subprocess.run(['/bin/ps','-axo','pid=,ppid=,command='],capture_output=True,text=True).stdout.splitlines()
        guard=None
        for line in rows:
            cols=line.split(None,2)
            if len(cols)==3 and '_owner-watchdog '+c['id']+' '+str(pid)+' ' in cols[2]: guard=cols[0]
        for line in rows:
            cols=line.split(None,2)
            if len(cols)==3 and cols[1]==guard and cols[2]=='sleep 2': return int(cols[0])
        return None
    check(eventually(lambda:guard_sleep() is not None,5),'guard enters its real two-second check sleep')
    first=guard_sleep(); lease.unlink(); log('Removed private owner lease for one guard evaluation')
    check(eventually(lambda:guard_sleep() not in (None,first),5),'guard completed one failed lease check and began next sleep')
    command(c,'reconcile')
    check(alive(pid) and not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'one failed lease check did not stop the runner')
    # Maintain owner through public reconcile long enough to observe recovery.
    stop=time.monotonic()+5
    while time.monotonic()<stop:
        command(c,'reconcile'); time.sleep(.5)
    check(alive(pid) and not nonempty(pathlib.Path(str(c['marker'])+'.signals')),'fresh owner lease resets failed-check debounce')
    command(c,'retire',c['id'])
    return dict(one_failed_check_survived=True,lease_recovery_survived=True)

try:
    log('Host '+subprocess.run(['uname','-a'],capture_output=True,text=True).stdout.strip())
    log('Base b84e0e362face25f3dd8945297a3df1320d7668c; target 46e578847c6a8ce11c18b2d48e5b6ffdb7d9d930')
    cases=[('base healthy reproduction',lambda:healthy('base')),('target healthy retirement',lambda:healthy('target')),
           ('base guard reproduction',lambda:guard('base')),('target guard expiry',lambda:guard('target')),
           ('target absent leader',lambda:retire_transition('attached')),('target Darwin zombie leader',lambda:retire_transition('zombie')),
           ('healthy reconcile cleanup',lambda:cleanup_path('reconcile')),('healthy home sweep',lambda:cleanup_path('sweep-home')),
           ('readable stale identity refusal',stale_identity),('external crash refusal all callers',crashed),('independent home scope',home_scope)]
    if MODE=='guard-clock': cases=[('target guard expiry corrected clock',lambda:guard('target'))]
    if MODE=='extra': cases=[('unreadable identity before and after proof',unavailable_identity),('live nonleader refusal',nonleader_identity),('single lease miss debounce',single_lease_miss)]
    for name,fn in cases:
        log('SCENARIO '+name)
        try: RESULTS.append(dict(name=name,result='pass',observations=fn()))
        except Exception as e:
            log('SCENARIO ERROR '+repr(e)); RESULTS.append(dict(name=name,result='fail',error=str(e))); traceback.print_exc(file=TRANSCRIPT)
finally:
    for c in ENVS:
        if 'release' in c: c['release'].touch()
    for pid in GROUPS:
        if alive(-pid):
            log('Cleanup exact test-owned group '+str(pid))
            try: os.killpg(pid,signal.SIGKILL)
            except ProcessLookupError: pass
    for p in CHILDREN:
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired: p.kill(); p.wait()
    time.sleep(2)
    leftovers=[pid for pid in GROUPS if alive(-pid)]
    log('Remaining test process groups: '+repr(leftovers))
    (EVIDENCE/('live-results.json' if MODE=='initial' else MODE+'-results.json')).write_text(json.dumps(dict(results=RESULTS,leftover_groups=leftovers),indent=2))
    TRANSCRIPT.close()
sys.exit(1 if any(r['result']=='fail' for r in RESULTS) or leftovers else 0)
