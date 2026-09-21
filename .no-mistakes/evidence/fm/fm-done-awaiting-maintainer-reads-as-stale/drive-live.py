import os, pathlib, subprocess, json, time, shlex, shutil, signal, traceback
ROOT=pathlib.Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M32BXAXR8VDP0RKGK8ST3RW6')
EVID=pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M32BXAXR8VDP0RKGK8ST3RW6')
WORK=ROOT/'.test-live'
SESSION='fm-lab-busy-health-89360-3170'
HELPER=ROOT/'bin/fm-herdr-lab.sh'
ENV=os.environ.copy()
for k in list(ENV):
    if k.startswith(('FM_', 'HERDR_', 'CLAUDE')) or k in ('TMUX','TMUX_PANE','TASKS_AXI_FILE','TASKS_AXI_BACKEND'):
        ENV.pop(k,None)
ENV.update(FM_HERDR_LAB_STATE_DIR=str(WORK/'lab-state'), SHELL='/bin/bash')
LOG=(EVID/'live-transcript.log').open('w',buffering=1)
PROCS=[]
def note(x):
    line=f'{time.strftime("%H:%M:%S")} {x}'
    print(line,flush=True); LOG.write(line+'\n')
def run(args,env=None,check=True):
    args=list(map(str,args)); r=subprocess.run(args,cwd=ROOT,env=env or ENV,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    note('$ '+shlex.join(args)+'\n'+r.stdout.rstrip()+f'\n[exit {r.returncode}]')
    if check and r.returncode: raise RuntimeError('command failed')
    return r.stdout
def lab(*args): return run([HELPER,'run',SESSION,*args])
def waitfor(fn,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if fn(): return
        time.sleep(.25)
    raise RuntimeError('condition timed out')
def start(args,env,path):
    handle=path.open('w'); p=subprocess.Popen(list(map(str,args)),cwd=ROOT,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    PROCS.append(p); return p
try:
    run([HELPER,'provision',SESSION])
    run([HELPER,'viewer','start',SESSION])
    info=json.loads(lab('workspace','create','--cwd',WORK,'--label','busy-health-test'))
    note('Workspace result '+json.dumps(info))
    panes=json.loads(lab('pane','list'))
    note('Pane inventory '+json.dumps(panes))
    # The new session has one default workspace and the test workspace; pick the
    # pane under the workspace created above, using immutable returned IDs.
    wid=info['result']['workspace']['workspace_id']
    ps=json.loads(lab('pane','list','--workspace',wid))['result']['panes']
    pane=ps[0]['pane_id']; target=SESSION+':'+pane
    state=WORK/'home/state'; job=WORK/'job'; config=WORK/'claude-config'; shim=WORK/'shim'
    for p in (state,job,config,shim,WORK/'home/config'): p.mkdir(parents=True,exist_ok=True)
    (shim/'herdr').write_text('#!/usr/bin/env python3\nimport os,sys\na=sys.argv[1:]\nif len(a)>=2 and a[-2:]==["--session",'+repr(SESSION)+']: a=a[:-2]\nif any(x=="--session" or x.startswith("--session=") for x in a): sys.exit(91)\nenv=os.environ.copy(); env["PATH"]='+repr(ENV['PATH'])+'\nos.execve('+repr(str(HELPER))+',["fm-herdr-lab.sh","run",'+repr(SESSION)+']+a,env)\n')
    (shim/'herdr').chmod(0o755)
    env=ENV.copy(); env.update(FM_HOME=str(WORK/'home'),FM_ROOT_OVERRIDE=str(WORK/'home'),FM_STATE_OVERRIDE=str(state),FM_CONFIG_OVERRIDE=str(WORK/'home/config'),FM_BACKEND='herdr',HERDR_SESSION=SESSION,PATH=str(shim)+':'+ENV['PATH'],FM_POLL='1',FM_SIGNAL_GRACE='1',FM_CHECK_INTERVAL='999999',FM_HEARTBEAT='999999',FM_BUSY_TURN_MAX_SECS='25',FM_STALE_ESCALATE_SECS='5',FM_CREW_STATE_NO_FORGE='1',FM_WEDGE_ALARM_EXEC='discard')
    (state/'busy.meta').write_text(f'window={target}\nbackend=herdr\nharness=claude\nkind=scout\nworktree={job}\n')
    (state/'busy.status').write_text('working: controlled shell command in the current turn\n')
    (state/'busy.turn-ended').touch(); old=time.time()-5705
    os.utime(state/'busy.turn-ended',(old,old)); os.utime(state/'busy.meta',(old,old))
    run([ROOT/'bin/fm-busy-event.sh','arm',state,'busy','--state','idle','--source','claude-hook','--event','Stop'],env)
    for name in ('busy.status','busy.turn-ended'):
        sig=run(['bash','-c','. "$1"; fm_wake_signal_sig "$2"','_',ROOT/'bin/fm-wake-lib.sh',state/name],env).strip()
        (state/('.seen-'+name.replace('.','_'))).write_text(sig)
    hook=WORK/'hold-hook.sh'
    hook.write_text('#!/bin/bash\n'+shlex.join([str(ROOT/'bin/fm-busy-event.sh'),'apply',str(state),'busy','busy','--current-gen','--source','claude-hook','--event','UserPromptSubmit'])+'\nprintf "real UserPromptSubmit hook: shell sleep active\\n"\nsleep 70\n')
    hook.chmod(0o755)
    idle=shlex.join([str(ROOT/'bin/fm-busy-event.sh'),'apply',str(state),'busy','idle','--current-gen','--source','claude-hook','--event','Stop'])
    settings=WORK/'claude-settings.json'; settings.write_text(json.dumps({'hooks':{'UserPromptSubmit':[{'hooks':[{'type':'command','command':str(hook),'timeout':120}]}],'Stop':[{'hooks':[{'type':'command','command':idle}]}],'StopFailure':[{'hooks':[{'type':'command','command':idle}]}],'SessionEnd':[{'hooks':[{'type':'command','command':idle}]}]}}))
    launch=WORK/'launch-claude.sh'
    launch.write_text('#!/bin/bash\ncd '+shlex.quote(str(job))+'\nexport CLAUDE_CONFIG_DIR='+shlex.quote(str(config))+'\nexport DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1\nexec '+shlex.join([shutil.which('claude'),'-p','--no-session-persistence','--setting-sources','','--settings',str(settings),'--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--tools','','--system-prompt','Reply OK only. Do not perform any actions.','Reply OK.'])+'\n')
    launch.chmod(0o755)
    lab('pane','run',pane,str(launch))
    waitfor(lambda: 'state=busy' in (state/'busy.busy-state').read_text(),25)
    note('CLAUDE_BUSY '+(state/'busy.busy-state').read_text().strip())
    lab('pane','process-info','--pane',pane)
    # Product reader and watcher are unmodified; no mocked state or backend.
    run([ROOT/'bin/fm-crew-state.sh','busy'],env)
    watchout=EVID/'live-busy-watch.log'; watcher=start([ROOT/'bin/fm-watch.sh'],env,watchout)
    time.sleep(12)
    note('FRESH_TURN watcher_alive='+str(watcher.poll() is None)+' wake_queue='+str((state/'.wake-queue').read_text() if (state/'.wake-queue').exists() else '<absent>'))
    assert watcher.poll() is None and not (state/'.wake-queue').exists(), 'fresh turn escalated'
    lab('pane','read',pane,'--format','text')
    waitfor(lambda: watcher.poll() is not None,40)
    note('AGED_TURN '+watchout.read_text())
    assert 'possible wedge' in watchout.read_text(), 'old turn did not wedge-escalate'
    note('WAKE_QUEUE '+(state/'.wake-queue').read_text())
    shutil.copy2(state/'.wake-queue',EVID/'live-busy-wake-queue.tsv')
    if (state/'.watch-triage.log').exists(): shutil.copy2(state/'.watch-triage.log',EVID/'live-busy-triage.log')
    lab('pane','process-info','--pane',pane)
    note('PASS: a fresh actual Claude UserPromptSubmit turn stays quiet, then its own age bound permits a wedge alarm.')
except Exception:
    note(traceback.format_exc())
    raise
finally:
    for p in PROCS:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try: p.wait(timeout=8)
            except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL); p.wait()
    run([HELPER,'teardown',SESSION],check=False)
    LOG.close()
