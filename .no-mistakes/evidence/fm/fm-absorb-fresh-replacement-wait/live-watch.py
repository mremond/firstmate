import os, pathlib, subprocess, time, json, re, shutil, datetime
ROOT = pathlib.Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M2FR2HYYDP8NP8HDDX4D1MXS')
EVID = pathlib.Path('/Users/mremond/.no-mistakes/evidence/01M2FR2HYYDP8NP8HDDX4D1MXS')
selection=os.environ.get('FM_LIVE_SELECT','')
results = json.loads((EVID/'live-results.json').read_text()) if selection else []
def say(s): print(s, flush=True)
def read(p): return p.read_text() if p.exists() else ''
def until(fn, timeout=45):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if fn(): return
        time.sleep(.1)
    raise AssertionError('condition did not become true within '+str(timeout)+'s')
class Case:
    def __init__(self, name):
        self.name=name; self.home=ROOT/'.phase-test'/(name+'-verified'); self.state=self.home/'state'
        for d in ('state','data','config'): (self.home/d).mkdir(parents=True, exist_ok=True)
        self.env={k:v for k,v in os.environ.items() if not k.startswith('FM_') and not k.startswith('TASKS_AXI')}
        self.env.update(FM_HOME=str(self.home), FM_ROOT_OVERRIDE=str(self.home), FM_STATE_OVERRIDE=str(self.state), FM_DATA_OVERRIDE=str(self.home/'data'), FM_CONFIG_OVERRIDE=str(self.home/'config'), FM_BACKEND='tmux', TMUX='.phase-test/t,0,0', FM_POLL='1', FM_SIGNAL_GRACE='1', FM_PAUSE_RESURFACE_SECS='240', FM_CHECK_INTERVAL='999999', FM_HEARTBEAT='999999', FM_HOME_SUMMARY_INTERVAL='999999', TMPDIR=str(ROOT/'.phase-test/tmp'))
        self.env['GIT_CEILING_DIRECTORIES']=str(ROOT/'.phase-test')
        self.status=self.state/'wait.status'; self.status.touch()
        (self.state/'wait.meta').write_text('window=phase:wait\nkind=ship\nharness=grok\nbackend=tmux\nworktree='+str(self.home)+'\n')
        self.proc=None; self.round=0
    def run(self, args, check=True):
        p=subprocess.run(args,cwd=ROOT,env=self.env,text=True,capture_output=True,timeout=45)
        say('$ '+' '.join(args)+'\n'+p.stdout+p.stderr)
        if check: assert p.returncode==0, (args,p.returncode,p.stderr)
        return p
    def append(self, line):
        # A task declares its wait through the real terminal's shell, just as a worker appends status.
        import shlex
        cmd='printf "%s\\n" '+shlex.quote(line)+' >> '+shlex.quote(str(self.status))
        self.run(['tmux','send-keys','-t','phase:wait','-l',cmd])
        self.run(['tmux','send-keys','-t','phase:wait','Enter'])
        until(lambda: line in read(self.status))
        say('STATUS '+read(self.status).strip())
    def age(self, seconds=500):
        stamp=time.time()-seconds; os.utime(self.status,(stamp,stamp))
        say('TEST DATA: persisted status mtime aged '+str(seconds)+'s; production clock unchanged')
        self.run(['bash','-c','. "$1"; fm_wake_status_mark_current "$2" "$3"','_',str(ROOT/'bin/fm-wake-lib.sh'),str(self.state),str(self.status)])
    def start(self):
        self.round+=1; self.out=EVID/(self.name+'-'+str(self.round)+'.watch.log')
        self.fp=self.out.open('w')
        env=dict(self.env,FM_WATCH_HANDLING_SUCCESSOR='1')
        self.proc=subprocess.Popen([str(ROOT/'bin/fm-watch.sh')],cwd=ROOT,env=env,stdout=self.fp,stderr=subprocess.STDOUT)
        say('START production bin/fm-watch.sh '+self.name+' round='+str(self.round))
    def exited(self, expected):
        until(lambda:self.proc.poll() is not None)
        self.fp.close()
        out=read(self.out); say('WATCH OUTPUT '+out.strip())
        assert self.proc.returncode==0, out
        assert expected in out, out
        queue=read(self.state/'.wake-queue'); say('PERSISTED WAKE QUEUE\n'+queue)
        assert len([l for l in queue.splitlines() if '\tstale\t' in l])==(0 if expected == 'signal:' else 1),queue
    def ack(self):
        p=self.run([str(ROOT/'bin/fm-wake-drain.sh')])
        m=re.search(r'WAKE_ACK_REQUIRED:.*--ack-through (\d+) --recovery-generation ([A-Za-z0-9._-]+)',p.stderr)
        assert m,p.stderr
        self.run([str(ROOT/'bin/fm-wake-drain.sh'),'--ack-through',m[1],'--recovery-generation',m[2]])
        assert not read(self.state/'.wake-queue').strip()
    def quiet(self, token):
        log=self.state/'.watch-triage.log'; old=read(log).count(token)
        until(lambda: self.proc.poll() is not None or read(log).count(token)>=old+2)
        assert self.proc.poll() is None,read(self.out)
        assert not read(self.state/'.wake-queue').strip(),read(self.state/'.wake-queue')
        say('PRODUCTION TRIAGE (two completed matching observations)\n'+'\n'.join(read(log).splitlines()[-6:]))
        say('THROTTLE '+read(self.state/'.paused-resurfaced-phase_wait'))
    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate(); self.proc.wait(timeout=15)
        if hasattr(self,'fp'): self.fp.close()
    def snapshot(self):
        dest=EVID/(self.name+'-state'); dest.mkdir(exist_ok=True)
        for name in ('wait.status','.wake-queue','.watch-triage.log','.paused-resurfaced-phase_wait','.last-watcher-beat','.afk-contract'):
            p=self.state/name
            if p.exists(): shutil.copy2(p,dest/name)

def execute(name, fn):
    if selection and name!=selection: return
    c=Case(name)
    try:
        c.run([str(ROOT/'bin/fm-crew-state.sh'),'wait'])
        fn(c); results.append(dict(name=name,result='pass',live=True)); say('SCENARIO PASS '+name)
    except Exception as e:
        results.append(dict(name=name,result='fail',live=True,error=str(e))); say('SCENARIO FAIL '+name+': '+str(e))
    finally:
        c.stop(); c.snapshot(); (EVID/'live-results.json').write_text(json.dumps(results,indent=2)+'\n')

def replacement(c, first, second):
    c.append(first); c.start(); c.exited('signal:'); c.ack()
    c.age(); c.start(); c.exited('stale: phase:wait'); c.ack()
    old=read(c.state/'.paused-resurfaced-phase_wait')
    c.append(second); c.start(); c.exited('signal:'); c.ack()
    c.start(); c.quiet('absorbed stale'); c.stop()
    assert read(c.state/'.paused-resurfaced-phase_wait')==old
    c.age(); c.start(); c.exited('stale: phase:wait'); c.ack()
    assert read(c.state/'.paused-resurfaced-phase_wait')!=old
    c.start(); c.quiet('absorbed stale'); c.stop()

execute('external-replacement',lambda c:replacement(c,'paused: waiting for validation one','paused: waiting for validation two'))
execute('captain-held-replacement',lambda c:replacement(c,'captain-held [key=route]: awaiting routing call','captain-held [key=release]: awaiting release call'))

def due(c):
    iso=lambda offset: datetime.datetime.fromtimestamp(time.time()+offset,datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    c.append('paused: wait A, until '+iso(-30)); c.start(); c.exited('signal:'); c.ack()
    c.start(); c.exited('declared clearing time has passed'); c.ack()
    c.start(); c.quiet('absorbed stale'); c.stop()
    c.append('paused: replacement B, until '+iso(-10)); c.start(); c.exited('signal:'); c.ack()
    c.start(); c.exited('declared clearing time has passed'); c.ack()
    c.start(); c.quiet('absorbed stale'); c.stop()
execute('expired-deadline-replacement',due)

def future(c):
    iso=datetime.datetime.fromtimestamp(time.time()+31536000,datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    c.append('paused: waiting for reset, until '+iso); c.start(); c.exited('signal:'); c.ack()
    c.start(); c.quiet('declared time not reached'); c.stop()
    c.age(); c.start(); c.exited('declared time is beyond the recheck cadence'); c.ack()
execute('future-deadline-cadence-cap',future)

def away(c):
    c.append('captain-held [key=hold]: awaiting user choice'); c.start(); c.exited('signal:'); c.ack()
    c.run([str(ROOT/'bin/fm-afk-contract.sh'),'propose'])
    c.run([str(ROOT/'bin/fm-afk-contract.sh'),'confirm'])
    c.age(); c.start(); c.quiet('never rechecked while the away-posture record exists'); c.stop()
    c.run([str(ROOT/'bin/fm-afk-contract.sh'),'archive'])
    c.start(); c.exited('stale: phase:wait'); c.ack()
execute('captain-held-away-boundary',away)
def crossing(c):
    deadline=time.time()+20
    iso=datetime.datetime.fromtimestamp(deadline,datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    c.append('paused: waiting for reset, until '+iso); c.start(); c.exited('signal:'); c.ack()
    c.start(); c.quiet('declared time not reached')
    assert time.time()<deadline, 'setup exceeded the chosen future deadline'
    say('DEADLINE TRANSITION: real wall clock crosses '+iso+' with the same watcher running')
    c.exited('declared clearing time has passed'); c.ack()
    c.start(); c.quiet('absorbed stale'); c.stop()
execute('deadline-crosses-while-watching',crossing)
say(json.dumps(results,indent=2))
raise SystemExit(any(r['result']=='fail' for r in results))
