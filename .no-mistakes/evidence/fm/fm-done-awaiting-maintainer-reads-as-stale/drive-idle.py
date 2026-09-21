# Real unmodified monitoring processes against an isolated Herdr pane.
import os, pathlib, subprocess, json, time, shlex, shutil, signal, traceback
ROOT=pathlib.Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M32BXAXR8VDP0RKGK8ST3RW6')
EVID=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M32BXAXR8VDP0RKGK8ST3RW6')
WORK=ROOT/'.test-live/idle'; WORK.mkdir(parents=True,exist_ok=True)
HELPER=ROOT/'bin/fm-herdr-lab.sh'; SESSION='fm-lab-unproven-89360'
ENV=os.environ.copy()
for k in list(ENV):
    if k.startswith(('FM_','HERDR_','CLAUDE')) or k in ('TMUX','TMUX_PANE','TASKS_AXI_FILE','TASKS_AXI_BACKEND'): ENV.pop(k,None)
ENV.update(FM_HERDR_LAB_STATE_DIR=str(WORK/'lab-state'),SHELL='/bin/bash')
LOG=(EVID/'live-idle-transcript.log').open('w',buffering=1); PROCS=[]; daemon_state=None

def note(x):
    line=f'{time.strftime("%H:%M:%S")} {x}'; print(line,flush=True); LOG.write(line+'\n')
def run(args,env=None,check=True):
    args=list(map(str,args)); r=subprocess.run(args,cwd=ROOT,env=env or ENV,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=40)
    note('$ '+shlex.join(args)+'\n'+r.stdout.rstrip()+f'\n[exit {r.returncode}]')
    if check and r.returncode: raise RuntimeError('command failed')
    return r.stdout
def lab(*args): return run([HELPER,'run',SESSION,*args])
def start(args,env,out):
    p=subprocess.Popen(list(map(str,args)),cwd=ROOT,env=env,stdout=out.open('w'),stderr=subprocess.STDOUT,start_new_session=True); PROCS.append(p); return p
def waitfor(fn,seconds=40):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if fn(): return
        time.sleep(.25)
    raise RuntimeError('condition timed out')
try:
    run([HELPER,'provision',SESSION]); run([HELPER,'viewer','start',SESSION])
    info=json.loads(lab('workspace','create','--cwd',WORK,'--label','unproven-worker'))['result']; pane=info['root_pane']['pane_id']; target=SESSION+':'+pane
    shim=WORK/'shim'; shim.mkdir(exist_ok=True)
    (shim/'herdr').write_text('#!/usr/bin/env python3\nimport os,sys\na=sys.argv[1:]\nif len(a)>=2 and a[-2:]==["--session",'+repr(SESSION)+']: a=a[:-2]\nif any(x=="--session" or x.startswith("--session=") for x in a): sys.exit(91)\nenv=os.environ.copy(); env["PATH"]='+repr(ENV['PATH'])+'\nos.execve('+repr(str(HELPER))+',["fm-herdr-lab.sh","run",'+repr(SESSION)+']+a,env)\n'); (shim/'herdr').chmod(0o755)
    common=ENV.copy(); common.update(PATH=str(shim)+':'+ENV['PATH'],FM_BACKEND='herdr',HERDR_SESSION=SESSION,FM_POLL='1',FM_SIGNAL_GRACE='1',FM_CHECK_INTERVAL='999999',FM_HEARTBEAT='999999',FM_STALE_ESCALATE_SECS='5',FM_CREW_STATE_NO_FORGE='1',FM_WEDGE_ALARM_EXEC='discard')
    def home_env(name):
        home=WORK/name; state=home/'state'; state.mkdir(parents=True,exist_ok=True); (home/'config').mkdir(exist_ok=True)
        (state/'unproven.meta').write_text(f'window={target}\nbackend=herdr\nharness=codex\nkind=ship\nworktree={ROOT}\n')
        env=common.copy(); env.update(FM_HOME=str(home),FM_ROOT_OVERRIDE=str(home),FM_STATE_OVERRIDE=str(state),FM_CONFIG_OVERRIDE=str(home/'config'))
        return state,env
    state,env=home_env('watch-home')
    verdict=run([ROOT/'bin/fm-crew-state.sh','unproven'],env)
    assert 'source: run-step' not in verdict, 'unexpected live-run discovery; revisit coverage'
    run(['no-mistakes','axi','status'],env,check=False)
    run(['no-mistakes','axi','status','--run','01M32BXAXR8VDP0RKGK8ST3RW6'],env)
    out=EVID/'live-unproven-watch.log'; p=start([ROOT/'bin/fm-watch.sh'],env,out)
    waitfor(lambda:p.poll() is not None)
    note('WATCHER_STDOUT '+out.read_text()); note('WATCHER_QUEUE '+(state/'.wake-queue').read_text())
    assert out.read_text().strip()=='stale: '+target
    shutil.copy2(state/'.wake-queue',EVID/'live-unproven-watch-queue.tsv')
    note('PASS: an unproven idle pane immediately produces a plain stale notification.')
    daemon_state,env=home_env('daemon-home'); (daemon_state/'.afk').touch()
    env.update(FM_DAEMON_PRIMARY_HARNESS='claude',FM_SUPERVISOR_BACKEND='herdr',FM_SUPERVISOR_TARGET=SESSION+':w1:p1',FM_ESCALATE_BATCH_SECS='999999',FM_MAX_DEFER_SECS='999999',FM_HOUSEKEEPING_TICK='1')
    out=EVID/'live-unproven-daemon.log'; p=start([ROOT/'bin/fm-supervise-daemon.sh'],env,out)
    buf=daemon_state/'.subsuper-escalations'
    waitfor(lambda:buf.exists() and 'possible wedge' in buf.read_text(),55)
    note('DAEMON_ESCALATION '+buf.read_text()); shutil.copy2(buf,EVID/'live-unproven-daemon-escalations.log')
    note('DAEMON_LOG '+(daemon_state/'.supervise-daemon.log').read_text()); shutil.copy2(daemon_state/'.supervise-daemon.log',EVID/'live-daemon-routing.log')
    note('PASS: the real away-mode daemon escalates a persistently unproven pane at its age threshold.')
except Exception:
    note(traceback.format_exc()); raise
finally:
    if daemon_state: (daemon_state/'.afk').unlink(missing_ok=True)
    for p in PROCS:
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    run([HELPER,'teardown',SESSION],check=False); LOG.close()
