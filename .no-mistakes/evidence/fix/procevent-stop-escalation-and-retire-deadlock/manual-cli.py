import json, os, signal, subprocess, sys, time
from pathlib import Path
ROOT=Path.cwd()
RUN=ROOT/'.local-procevent-validation/manual'
EVIDENCE=Path('/Users/mremond/.no-mistakes/evidence/01M22JMZFHHKDEBP264VCZFC1C')
RUN.mkdir(parents=True,exist_ok=True)
os.umask(0o022)
results=[]

def alive(pid):
    try: os.kill(pid,0); return True
    except ProcessLookupError: return False

def wait_for(f, seconds=60):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if f(): return
        time.sleep(.1)
    raise AssertionError('condition did not become true within '+str(seconds)+'s')

def say(s): print(s,flush=True)

def pe(home,*args):
    env=os.environ.copy()
    env.update(FM_HOME=str(home), FM_PROCEVENT_CLAIM_ROOT=str(home/'claims'),
               FM_PROCEVENT_OWNER_LEASE_SECONDS='5',FM_PROCEVENT_OWNER_CHECK_SECONDS='1',
               FM_GATE_REFUSE_BYPASS='1',TMPDIR=str(RUN))
    c=[str(ROOT/'bin/fm-procevent.sh'),*args]
    say('$ FM_HOME='+str(home)+' fm-procevent.sh '+' '.join(args))
    start=time.monotonic()
    p=subprocess.run(c,env=env,capture_output=True,text=True,timeout=75)
    say(p.stdout+p.stderr+f'[exit={p.returncode}, elapsed={time.monotonic()-start:.3f}s]')
    return p

def start(name, lease='5',attached=False):
    h=RUN/name; (h/'state').mkdir(parents=True)
    p=pe(h,'register','lavish',name,'--','/bin/sleep','180'); assert p.returncode==0
    env=os.environ.copy(); env.update(FM_HOME=str(h),FM_PROCEVENT_CLAIM_ROOT=str(h/'claims'),
        FM_PROCEVENT_OWNER_LEASE_SECONDS=lease, FM_PROCEVENT_OWNER_CHECK_SECONDS='1',
        FM_GATE_REFUSE_BYPASS='1',TMPDIR=str(RUN))
    log=(h/'launch.log').open('w')
    launch=subprocess.Popen([str(ROOT/'bin/fm-procevent.sh'),'start' if attached else 'reconcile',name] if attached else [str(ROOT/'bin/fm-procevent.sh'),'reconcile'],env=env,stdout=log,stderr=log)
    rec=h/'state/procevent'/f'{name}.runner'
    claim=h/'claims'/f'{name}.claim'
    wait_for(lambda:rec.exists() and rec.stat().st_size>0)
    pid=int(rec.read_text().strip())
    wait_for(lambda:bool(subprocess.run(['/bin/ps','-o','pid=','-g',str(pid)],capture_output=True,text=True).stdout.strip()))
    time.sleep(1)
    say('START '+name+' '+subprocess.check_output(['/bin/ps','-p',str(pid),'-o','pid=,ppid=,pgid=,stat=,command='],text=True).strip())
    return h,pid,claim,launch,log

def cleanup(h,pid,launch,log):
    if alive(-pid):
        os.killpg(pid,signal.SIGKILL)
        wait_for(lambda:not alive(-pid),20)
    try: launch.wait(timeout=20)
    except subprocess.TimeoutExpired: launch.kill(); launch.wait()
    pe(h,'retire',h.name)
    log.close()

for name in ['reconcile-healthy','crashed-group','mismatched-live','nonleader-live']:
    h=None
    try:
        h,pid,claim,launch,log=start(name,lease='5' if name=='crashed-group' else '600',attached=name=='reconcile-healthy')
        source=h/'state/procevent'/f'{name}.source'
        if name=='reconcile-healthy':
            source.unlink()
            out=pe(h,'reconcile')
            status=launch.wait(timeout=30)
            say(f'Attached start returned {status}; group_alive={alive(-pid)}; claim_exists={claim.exists()}')
            assert out.returncode==0 and 'stopped=1' in out.stdout and status==143 and not alive(-pid) and not claim.exists()
        elif name=='crashed-group':
            original=claim.read_bytes()
            os.kill(pid,signal.SIGKILL)
            wait_for(lambda:not alive(pid),20)
            assert alive(-pid)
            say('Independent SIGKILL: leader absent; its sleep child and group remain alive.')
            for args in [('retire',name),('reconcile',),('sweep-home',)]:
                out=pe(h,*args)
                assert alive(-pid) and claim.read_bytes()==original and source.exists()
                if args[0]!='reconcile': assert out.returncode!=0
                else: assert 'started=0' in out.stdout
                say('Preserved the original claim and registration; group still alive; no replacement.')
            # No home operation refreshes the lease during this observation.
            time.sleep(10)
            assert alive(-pid) and claim.read_bytes()==original and source.exists()
            say('After lease expiry plus two guard checks: group still alive, claim unchanged.')
        else:
            os.kill(pid,signal.SIGSTOP)
            lines=claim.read_text().splitlines()
            if name=='mismatched-live':
                lines[3]='different-live-process-identity'
            else:
                # A real nonleader process moves the recorded pid into a group it does not lead.
                child=int(subprocess.check_output(['/bin/ps','-o','pid=','-g',str(pid)],text=True).split()[-1])
                assert child!=pid and os.getpgid(child)==pid
                lines[1]=str(child)
                lines[3]=subprocess.check_output(['/bin/ps','-p',str(child),'-o','lstart=','-o','command='],text=True,env={**os.environ,'LC_ALL':'C'}).strip()
                say(f'Recorded real nonleader pid={child}, kernel pgid={os.getpgid(child)}')
            claim.write_text('\n'.join(lines)+'\n'); claim.chmod(0o600)
            before=claim.read_bytes()
            out=pe(h,'retire',name)
            say(f'Unproved first signal: group_alive={alive(-pid)}, registration_exists={source.exists()}, claim_unchanged={claim.read_bytes()==before}')
            assert out.returncode!=0 and alive(-pid) and source.exists() and claim.read_bytes()==before
        results.append({'name':name,'result':'pass'})
        say('SCENARIO PASSED: '+name)
    except Exception as e:
        results.append({'name':name,'result':'fail','error':repr(e)}); say('SCENARIO FAILED: '+name+' '+repr(e))
    finally:
        if h: cleanup(h,pid,launch,log)
(EVIDENCE/'manual-results.json').write_text(json.dumps(results,indent=2)+'\n')
sys.exit(any(r['result']=='fail' for r in results))
