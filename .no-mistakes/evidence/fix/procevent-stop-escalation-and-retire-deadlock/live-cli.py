import os, signal, subprocess as sp, time, json, pathlib, shutil, traceback
ROOT=pathlib.Path.cwd()
E=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M2414ECRE7T77CAXN49RSA2F')
W=ROOT/'.test-phase-tmp'/'live-cli'
W.mkdir(parents=True,exist_ok=True)
ENV={k:v for k,v in os.environ.items() if not k.startswith('FM_')}
ENV.update(FM_PROCEVENT_CLAIM_ROOT=str(W/'claims'),TMPDIR=str(W),FM_GATE_REFUSE_BYPASS='1')
SCRIPT=str(ROOT/'bin/fm-procevent.sh')
results=[]; groups=set(); homes=[]; processes=[]
def log(s): print(s,flush=True)
def wait_for(fn,seconds=15,label='condition'):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=fn()
        if value:return value
        time.sleep(.04)
    raise AssertionError('Timed out: '+label)
def alive(pid):
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
def group_alive(pid):
    try:os.killpg(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True  # transient kernel teardown; never count as gone
def env(home,**extra):return dict(ENV,FM_HOME=str(home),**{k:str(v) for k,v in extra.items()})
def pe(home,*args,extra=None,ok=True):
    log('$ FM_HOME='+home.name+' fm-procevent.sh '+' '.join(args))
    p=sp.run([SCRIPT,*args],env=env(home,**(extra or {})),capture_output=True,text=True,timeout=25)
    log((p.stdout+p.stderr).strip()+f' [exit {p.returncode}]')
    if ok:assert p.returncode==0,p.stderr
    return p

def home(name):
    h=W/name;h.mkdir();homes.append(h);return h

def start(h,id,argv,check='4',lease='60',attached=False):
    pe(h,'register','lavish',id,'--',*map(str,argv))
    extra=dict(FM_PROCEVENT_OWNER_CHECK_SECONDS=check,FM_PROCEVENT_OWNER_LEASE_SECONDS=lease)
    p=None
    if attached:
        f=open(h/'attached.log','w');p=sp.Popen([SCRIPT,'start',id],env=env(h,**extra),stdout=f,stderr=sp.STDOUT);processes.append(p)
    else:pe(h,'reconcile',extra=extra)
    f=h/'state'/'procevent'/f'{id}.runner'
    pid=int(wait_for(lambda:f.read_text().strip() if f.exists() else None,label=id+' runner'))
    groups.add(pid)
    return pid,p

def table():
    out=sp.check_output(['/bin/ps','-axo','pid=,ppid=,pgid=,stat=,command='],text=True)
    rows=[]
    for line in out.splitlines():
        a=line.strip().split(None,4)
        if len(a)==5:rows.append((int(a[0]),int(a[1]),int(a[2]),a[3],a[4]))
    return rows

def snapshot(pid,label):
    rows=[r for r in table() if r[2]==pid or ('_owner-watchdog ' in r[4] and f' {pid} ' in r[4])]
    log(label+'\n'+'\n'.join(map(str,rows)))

def guard(pid):
    return wait_for(lambda:next((r[0] for r in table() if '_owner-watchdog ' in r[4] and f' {pid} ' in r[4]),None),label='owner guard')
def sleeper(g,exclude=None):
    return next((r for r in table() if r[1]==g and r[0]!=exclude and r[4].startswith('sleep ')),None)
def next_sleep(g,old=None):return wait_for(lambda:sleeper(g,old),label='next actual guard sleep')
def retired(h,id,pid,p=None):
    t=time.monotonic();pe(h,'retire',id);elapsed=time.monotonic()-t
    wait_for(lambda:not group_alive(pid),label='group extinction')
    if p is not None:
        status=p.wait(timeout=5);log(f'attached start exit={status}; retire={elapsed:.3f}s');assert status==143,status
    assert not (h/'state'/'procevent'/f'{id}.source').exists()
    return elapsed

def case(name,fn):
    if os.environ.get('ONLY_SCENARIO') and not any(x in name for x in os.environ['ONLY_SCENARIO'].split('|')):return
    log('\nSCENARIO: '+name)
    try:
        detail=fn();results.append(dict(name=name,result='pass',live=True,detail=detail));log('OBSERVED: '+str(detail))
    except Exception as ex:
        results.append(dict(name=name,result='fail',live=True,detail=str(ex)));traceback.print_exc();raise

inputfile=W/'follow.log';inputfile.write_text('')
poll=E/'deferred-poll.sh'
poll.write_text('''#!/bin/bash
marker=$1
input=$2
trap 'printf "TERM trap handled\\n" >> "$marker.trap"' TERM
/bin/sh -c 'trap "" TERM; printf "%s\\n" "$$" > "$1.child"; exec /usr/bin/tail -f "$2"' _ "$marker" "$input"
printf 'foreground child returned\\n' >> "$marker.returned"
''')
poll.chmod(0o700)

def deferred():
    marker=W/'deferred';f=open(W/'deferred.out','w')
    p=sp.Popen([str(poll),str(marker),str(inputfile)],env=ENV,start_new_session=True,stdout=f,stderr=sp.STDOUT);processes.append(p);groups.add(p.pid)
    child=int(wait_for(lambda:pathlib.Path(str(marker)+'.child').read_text() if pathlib.Path(str(marker)+'.child').exists() else None))
    os.kill(p.pid,signal.SIGTERM);time.sleep(.5)
    assert p.poll() is None and alive(child) and not pathlib.Path(str(marker)+'.trap').exists()
    log(f'TERM sent to shell pid={p.pid}; blocked tail pid={child}; after 0.5s both alive, trap has not run')
    os.kill(child,signal.SIGTERM);time.sleep(.3);assert alive(child)
    os.kill(child,signal.SIGKILL);p.wait(timeout=5)
    trap=pathlib.Path(str(marker)+'.trap').read_text().strip();assert trap=='TERM trap handled'
    return 'Shell deferred its TERM trap until the genuinely blocked tail child was killed; '+trap

def healthy():
    h=home('healthy');pid,p=start(h,'live-healthy',['/usr/bin/tail','-f',str(inputfile)],attached=True)
    snapshot(pid,'Before retire')
    elapsed=retired(h,'live-healthy',pid,p)
    return f'Healthy tail source and group exited on TERM; attached start=143, retirement={elapsed:.3f}s'

def escalation():
    h=home('blocked-retire');marker=h/'poll';pid,p=start(h,'live-blocked',[poll,marker,inputfile],attached=True)
    child=int(wait_for(lambda:pathlib.Path(str(marker)+'.child').read_text() if pathlib.Path(str(marker)+'.child').exists() else None))
    snapshot(pid,'Blocked foreground child before retirement')
    t=time.monotonic();stop=sp.Popen([SCRIPT,'retire','live-blocked'],env=env(h),stdout=sp.PIPE,stderr=sp.STDOUT,text=True);processes.append(stop)
    wait_for(lambda:not alive(pid),label='TERM ends the identified runner')
    assert alive(child),'No child survived TERM'
    assert not pathlib.Path(str(marker)+'.trap').exists(),'Foreground trap unexpectedly ran'
    snapshot(pid,'Runner gone, real tail still survives TERM before escalation')
    output=stop.communicate(timeout=15)[0];elapsed=time.monotonic()-t;log(output.strip()+f' [exit {stop.returncode}, {elapsed:.3f}s]')
    assert stop.returncode==0 and not alive(child)
    wait_for(lambda:not group_alive(pid),label='escalation extinguishes group')
    p.wait(timeout=5)
    return f'TERM ended runner while blocked tail survived; KILL then removed full group in {elapsed:.3f}s'

def decimal():
    values=[]
    for val,half in [('08','4'),('010','5'),('1','0.5'),('3','1.5')]:
        h=home('interval-'+val);pid,p=start(h,'live-interval-'+val,['/usr/bin/tail','-f',str(inputfile)],check=val)
        g=guard(pid);s=next_sleep(g);log(f'configured={val}; real guard child: {s}')
        assert s[4]=='sleep '+half,s
        assert any(r[2]==pid and '/usr/bin/tail -f ' in r[4] for r in table())
        retired(h,'live-interval-'+val,pid)
        values.append(val+' -> '+half+'s')
    return '; '.join(values)+'; every listener started and retired'

def debounce():
    h=home('debounce');pid,p=start(h,'live-debounce',['/usr/bin/tail','-f',str(inputfile)])
    g=guard(pid)
    for kind in ['lease','state root']:
        old=next_sleep(g)
        original=h/'state'/'procevent'/'.owner-lease' if kind=='lease' else h/'state'
        saved=h/('saved-lease' if kind=='lease' else 'saved-state')
        original.rename(saved);log(f'{kind} unavailable during guard sleep pid={old[0]}')
        try:
            new=next_sleep(g,old[0]);assert group_alive(pid)
            log(f'guard completed the failed read and started next sleep pid={new[0]}; runner remains alive')
        finally:saved.rename(original)
        next1=next_sleep(g,new[0]);next2=next_sleep(g,next1[0]);assert group_alive(pid)
        log(f'{kind} restored; two more read cycles completed; group {pid} alive')
    old=next_sleep(g);original=h/'state'/'procevent'/'.owner-lease';saved=h/'persistent-missing-lease';original.rename(saved)
    t=time.monotonic();new=next_sleep(g,old[0]);assert group_alive(pid)
    wait_for(lambda:not group_alive(pid),seconds=9,label='two consecutive unavailable reads stop runner')
    elapsed=time.monotonic()-t;saved.rename(original)
    log(f'Persistent missing lease: group stopped after {elapsed:.3f}s; alive after first failed read')
    pe(h,'retire','live-debounce')
    return 'Single missing lease and single unavailable state-root read each preserved the listener; two consecutive missing lease reads stopped it'

def bound():
    h=home('expiry');keep=home('keep-live')
    keeper,kp=start(keep,'live-keeper',['/usr/bin/tail','-f',str(inputfile)],check='4',lease='2',attached=True)
    pid,p=start(h,'live-expiry',['/usr/bin/tail','-f',str(inputfile)],check='4',lease='2')
    lease=float((h/'state'/'procevent'/'.owner-lease').read_text())
    snapshot(pid,'Detached expiring source')
    row=next(r for r in table() if r[0]==pid);assert row[1]==1
    wait_for(lambda:not group_alive(pid),seconds=10,label='lease expiry stops orphan')
    now=float(sp.check_output(['/usr/bin/perl','-MTime::HiRes=clock_gettime,CLOCK_MONOTONIC','-e','print clock_gettime(CLOCK_MONOTONIC)'],text=True))
    elapsed=now-lease;assert elapsed<10,elapsed
    assert group_alive(keeper),'Other live home was killed'
    log(f'Last-owner-activity to observed extinction={elapsed:.3f}s; documented healthy bound=2+1+4+1=8s; deadline with additive slack=10s')
    retired(keep,'live-keeper',keeper,kp);pe(h,'retire','live-expiry')
    return f'Orphan stopped {elapsed:.3f}s after lease refresh; independently refreshed home remained alive'

def refusal():
    h=home('cold-leaderless');pid,p=start(h,'live-cold',['/usr/bin/tail','-f',str(inputfile)])
    wait_for(lambda:any(r[2]==pid and r[4].startswith('/usr/bin/tail -f ') for r in table()),label='real source has actually started before killing leader')
    os.kill(pid,signal.SIGKILL);wait_for(lambda:not alive(pid),label='unrelated crash ends leader');assert group_alive(pid)
    out=pe(h,'retire','live-cold',ok=False)
    assert out.returncode!=0 and 'cannot confirm runner identity' in out.stderr+out.stdout
    assert group_alive(pid) and (h/'state'/'procevent'/'live-cold.source').exists()
    snapshot(pid,'Unproved surviving group untouched after retirement refusal')
    os.killpg(pid,signal.SIGKILL);wait_for(lambda:not group_alive(pid))
    pe(h,'retire','live-cold')
    return 'Unrelated leader death refused retirement, preserved registration, and left the unproved group untouched; test owner then cleaned it up'

def blocked_guard():
    h=home('blocked-expiry');marker=h/'poll';pid,p=start(h,'live-blocked-expiry',[poll,marker,inputfile],check='4',lease='2')
    child=int(wait_for(lambda:pathlib.Path(str(marker)+'.child').read_text() if pathlib.Path(str(marker)+'.child').exists() else None))
    lease=float((h/'state'/'procevent'/'.owner-lease').read_text())
    snapshot(pid,'Expired-owner test with genuinely blocked foreground child')
    wait_for(lambda:not alive(pid),seconds=10,label='owner guard sends TERM')
    assert alive(child),'No blocked child survived the owner guard TERM'
    log(f'Guard TERM ended runner {pid}, blocked tail {child} still alive')
    wait_for(lambda:not group_alive(pid),seconds=10,label='owner guard escalates and extinguishes group')
    assert not alive(child)
    now=float(sp.check_output(['/usr/bin/perl','-MTime::HiRes=clock_gettime,CLOCK_MONOTONIC','-e','print clock_gettime(CLOCK_MONOTONIC)'],text=True))
    elapsed=now-lease;log(f'Blocked orphan group gone {elapsed:.3f}s after last owner activity; bound=2+1+4+4=11s plus 2s additive slack');assert elapsed<13
    pe(h,'retire','live-blocked-expiry')
    return f'Owner expiry triggered TERM then KILL; blocked child and group gone after {elapsed:.3f}s'

def reconcile_cleanup():
    h=home('reconcile-stop');marker=h/'poll';pid,p=start(h,'live-reconcile',[poll,marker,inputfile])
    child=int(wait_for(lambda:pathlib.Path(str(marker)+'.child').read_text() if pathlib.Path(str(marker)+'.child').exists() else None))
    (h/'state'/'procevent'/'live-reconcile.source').unlink()
    t=time.monotonic();out=pe(h,'reconcile');elapsed=time.monotonic()-t
    assert 'stopped=1 uncertain=0' in out.stdout and not group_alive(pid) and not alive(child)
    pe(h,'register','lavish','live-reconcile','--','/usr/bin/tail','-f',str(inputfile))
    pe(h,'reconcile')
    newfile=h/'state'/'procevent'/'live-reconcile.runner'
    new=int(wait_for(lambda:newfile.read_text() if newfile.exists() else None));groups.add(new);assert new!=pid
    wait_for(lambda:any(r[2]==new and r[4].startswith('/usr/bin/tail -f ') for r in table()),label='replacement is listening')
    assert not group_alive(pid)
    retired(h,'live-reconcile',new)
    return f'Reconcile stopped blocked unregistered group in {elapsed:.3f}s; later re-registration started one new generation after old group extinction'

try:
    case('Expired blocked source is reaped by its owner guard',blocked_guard)
    case('Reconcile stops blocked unregistered source before re-registration',reconcile_cleanup)
    case('Deferred TERM trap with a genuinely blocked foreground tail',deferred)
    case('Retire healthy source without forced-kill deadlock',healthy)
    case('Retire blocked source after TERM ends its proved leader',escalation)
    case('Accepted decimal and odd intervals run with exact half spacing',decimal)
    case('Isolated unreadable owner inputs preserve service; repeated failure stops it',debounce)
    case('Expired detached source stops while another live home survives',bound)
    case('Unproved cold leaderless group is refused without signalling',refusal)
finally:
    for pid in groups:
        if group_alive(pid):
            try:os.killpg(pid,signal.SIGKILL)
            except ProcessLookupError:pass
    for p in processes:
        try:p.wait(timeout=3)
        except sp.TimeoutExpired:p.kill();p.wait()
    for h in homes:
        try:sp.run([SCRIPT,'sweep-home'],env=env(h),stdout=sp.DEVNULL,stderr=sp.DEVNULL,timeout=10)
        except Exception:pass
    (E/'live-cli-results.json').write_text(json.dumps(results,indent=2)+'\n')
    time.sleep(1)
    leftovers=[r for r in table() if str(W) in r[4] and r[0]!=os.getpid()]
    log('Remaining processes referencing the isolated test home: '+repr(leftovers))
    assert not leftovers,leftovers
    shutil.rmtree(W)
