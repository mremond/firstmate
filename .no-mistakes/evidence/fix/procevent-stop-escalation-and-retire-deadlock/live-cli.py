#!/usr/bin/env python3
"""Drive real process-event CLI; listener executables use the investigation's signal behavior.
No runner, watchdog, process-inspection, lock, or CLI command is mocked.
All runtime state and the base revision are under the gate worktree.
"""
import json, os, signal, subprocess, sys, time
from pathlib import Path
ROOT=Path.cwd()
EVIDENCE=Path('/Users/mremond/.no-mistakes/evidence/01M20TSCZM0KDMYBZKD1S7KSYQ')
RUNTIME=ROOT/'.local-test-procevent'
LOG=(EVIDENCE/'live-cli.log').open('w',buffering=1)
RESULTS=[]
def log(s): print(s,flush=True); LOG.write(s+'\n')
def waitfor(fn,seconds=15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if fn(): return True
        time.sleep(.05)
    return False
def alive(pid):
    try: os.kill(pid,0); return True
    except ProcessLookupError: return False
def ps(pid):
    return subprocess.run(['/bin/ps','-p',str(pid),'-o','pid=,ppid=,pgid=,stat=,command='],text=True,capture_output=True).stdout.strip()
S=(ROOT/'tests/fm-procevent.test.sh').read_text()
for name,marker in [('quiet','QUIET_STUB="$TMP_ROOT/quiet-stub.sh"'),('resistant','SIGNAL_PROOF_STUB="$TMP_ROOT/signal-proof-stub.sh"')]:
    text=S[S.index(marker):]
    body=text.split("<<'SH'\n",1)[1].split('\nSH\n',1)[0]+'\n'
    p=RUNTIME/(name+'.sh'); p.write_text(body); p.chmod(0o755)
class Case:
    def __init__(self,version,name,mode='resistant',lease=60,tick=1):
        self.version=version; self.name=name; self.id=version+'-'+name
        self.home=RUNTIME/self.id; (self.home/'state').mkdir(parents=True,exist_ok=True)
        self.marker=self.home/'poll'; self.claimroot=self.home/'claims'
        self.reg=self.home/'state/procevent'; self.source=self.reg/(self.id+'.source')
        self.claim=self.claimroot/(self.id+'.claim')
        self.code=ROOT if version=='target' else RUNTIME/'base'
        self.cli=self.code/'bin/fm-procevent.sh'
        self.env=os.environ.copy()
        for key in ['FM_STATE_OVERRIDE','FM_ROOT_OVERRIDE','FM_PROCEVENT_IN_RUNNER','FM_PROCEVENT_RUNNER_GROUP','FM_PROC_ROOT_OVERRIDE']:
            self.env.pop(key,None)
        self.env.update(FM_HOME=str(self.home),FM_PROCEVENT_CLAIM_ROOT=str(self.claimroot),FM_PROCEVENT_OWNER_LEASE_SECONDS=str(lease),FM_PROCEVENT_OWNER_CHECK_SECONDS=str(tick),FM_TEST_STUB_MAX_BLOCK_SECONDS='120',TMPDIR=str(RUNTIME/'tmp'))
        self.pid=None; self.parent=None; self.mode=mode
        self.output=(EVIDENCE/(self.id+'-start.log')).open('w')
    def cmd(self,*args):
        start=time.monotonic()
        p=subprocess.run([str(self.cli),*args],env=self.env,text=True,capture_output=True,timeout=25)
        duration=time.monotonic()-start
        log(f'[{self.id}] $ fm-procevent.sh {" ".join(args)} => status={p.returncode} elapsed={duration:.3f}s\n{p.stdout.strip()}\n{p.stderr.strip()}')
        return p,duration
    def start(self,attached=False,zombie=False):
        p,_=self.cmd('register','lavish',self.id,'--',str(RUNTIME/(self.mode+'.sh')),str(self.marker)); assert p.returncode==0
        if zombie:
            self.release=self.home/'reap'
            program='''my $release=shift @ARGV; defined(my $pid=fork) or exit 125;
if($pid==0){setpgrp(0,0) or exit 125; $ENV{FM_PROCEVENT_RUNNER_GROUP}=$$; exec @ARGV; exit 125;}
my $until=time+120; while(!-e $release && time<$until){select undef,undef,undef,0.05;} waitpid($pid,0);'''
            self.parent=subprocess.Popen(['perl','-e',program,str(self.release),str(self.cli),'_start',self.id],env=self.env,stdout=self.output,stderr=subprocess.STDOUT)
        elif attached:
            self.parent=subprocess.Popen([str(self.cli),'start',self.id],env=self.env,stdout=self.output,stderr=subprocess.STDOUT)
        else:
            p,_=self.cmd('reconcile'); assert p.returncode==0
        marker=Path(str(self.marker)+('.child' if self.mode=='resistant' else '.descendant'))
        assert waitfor(lambda:self.claim.exists() and marker.exists() and bool(marker.read_text().strip())), 'listener did not start'
        self.pid=int(self.claim.read_text().splitlines()[1]); self.child=int(marker.read_text())
        self.ready=time.monotonic()
        log(f'[{self.id}] runner: {ps(self.pid)}\n[{self.id}] listener/descendant: {ps(self.child)}')
    def signals(self):
        p=Path(str(self.marker)+'.signals'); return p.read_text().splitlines() if p.exists() else []
    def cleanup(self):
        if self.pid and alive(-self.pid):
            log(f'[{self.id}] teardown-only KILL of test-owned group {self.pid}')
            os.killpg(self.pid,signal.SIGKILL)
        if hasattr(self,'release'): self.release.touch()
        if self.parent:
            try:self.parent.wait(timeout=10)
            except subprocess.TimeoutExpired:self.parent.kill();self.parent.wait()
        if self.pid: assert waitfor(lambda:not alive(-self.pid),10), 'test cleanup left group alive'
        self.output.close()

def result(name,ok,**data):
    r=dict(name=name,passed=bool(ok),**data); RESULTS.append(r); log('OBSERVATION '+json.dumps(r)); return r

def healthy(version,action='retire'):
    c=Case(version,'healthy-'+action,mode='quiet')
    try:
        c.start(attached=True)
        if action=='reconcile': c.source.unlink(); log(f'[{c.id}] removed this test source registration before reconcile')
        p,d=c.cmd(action,*([c.id] if action=='retire' else []))
        status=c.parent.wait(timeout=10)
        gone=waitfor(lambda:not alive(-c.pid),5)
        result(c.id,p.returncode==0 and status==143 and gone,cli_status=p.returncode,start_exit_status=status,retirement_seconds=round(d,3),group_gone=gone,claim_removed=not c.claim.exists())
    finally:c.cleanup()

def guard(version):
    c=Case(version,'owner-expiry',lease=5,tick=1)
    keep=Case(version,'other-live-home',mode='quiet',lease=5,tick=1)
    try:
        keep.start(attached=True); c.start()
        c.cmd('reconcile'); start=time.monotonic()
        signalled=waitfor(lambda:bool(c.signals()),18)
        term_after=time.monotonic()-start
        gone=waitfor(lambda:not alive(-c.pid),12)
        elapsed=time.monotonic()-start
        log(f'[{c.id}] after TERM: runner={ps(c.pid) or "absent"}; child={ps(c.child) or "absent"}; signals={c.signals()}')
        other_alive=alive(keep.child) and alive(keep.pid)
        result(c.id,signalled and gone and other_alive,term_after_seconds=round(term_after,3),observed_seconds=round(elapsed,3),group_gone=gone,child_alive=alive(c.child),other_home_alive=other_alive,lease_seconds=5,check_seconds=1,signals=c.signals())
    finally:c.cleanup();keep.cleanup()

def resistant(action,zombie=False):
    c=Case('target',('zombie-' if zombie else 'resistant-')+action)
    try:
        c.start(attached=not zombie,zombie=zombie)
        if action=='reconcile':c.source.unlink()
        args=[str(c.cli),action]+([c.id] if action=='retire' else [])
        start=time.monotonic(); stop=subprocess.Popen(args,env=c.env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        transition=waitfor(lambda:(' Z' in ps(c.pid)) if zombie else not alive(c.pid),7)
        survivor=alive(c.child)
        log(f'[{c.id}] TERM transition: runner={ps(c.pid) or "absent"}; child={ps(c.child) or "absent"}; signals={c.signals()}')
        child_gone=waitfor(lambda:not alive(c.child),8)
        if zombie:c.release.touch();c.parent.wait(timeout=10)
        out,err=stop.communicate(timeout=12); d=time.monotonic()-start
        log(f'[{c.id}] $ fm-procevent.sh {" ".join(args[1:])} => status={stop.returncode} elapsed={d:.3f}s\n{out.strip()}\n{err.strip()}')
        group_gone=waitfor(lambda:not alive(-c.pid),5)
        result(c.id,transition and survivor and child_gone and group_gone and stop.returncode==0 and bool(c.signals()),leader_transition_observed=transition,survivor_after_TERM=survivor,child_gone=child_gone,group_gone=group_gone,cli_status=stop.returncode,seconds=round(d,3),claim_removed=not c.claim.exists())
    finally:c.cleanup()

def crash():
    c=Case('target','external-leader-crash',lease=5,tick=1)
    try:
        c.start();original_claim=c.claim.read_bytes()
        os.kill(c.pid,signal.SIGKILL); assert waitfor(lambda:not alive(c.pid),5)
        log(f'[{c.id}] external KILL of leader only; child still running: {ps(c.child)}')
        outcomes={}
        for action in ['retire','reconcile','sweep-home']:
            p,_=c.cmd(action,*([c.id] if action=='retire' else []))
            outcomes[action]=dict(status=p.returncode,group_alive=alive(-c.pid),claim_preserved=c.claim.read_bytes()==original_claim,registration_preserved=c.source.exists())
        # No further lease refresh. Guard must preserve the cold leaderless group too.
        time.sleep(9)
        guard_refused=alive(c.child) and not c.signals()
        Path(str(c.marker)+'.trigger').touch()
        assert waitfor(lambda:not alive(c.child),5)
        results=list((c.home/'state/procevent-inbox').glob('*.result'))
        wakes=c.home/'state/.wake-queue'
        no_capture=not results and (not wakes.exists() or not wakes.read_bytes())
        ok=outcomes['retire']['status']!=0 and outcomes['sweep-home']['status']!=0 and all(v['group_alive'] and v['claim_preserved'] and v['registration_preserved'] for v in outcomes.values()) and guard_refused and no_capture
        result(c.id,ok,callers=outcomes,guard_did_not_signal=guard_refused,completed_child_output_lost=no_capture)
    finally:c.cleanup()

def mismatch():
    c=Case('target','first-signal-mismatch')
    try:
        c.start(); rows=c.claim.read_text().splitlines(); original=list(rows)
        rows[3]='different-live-process-identity';c.claim.write_text('\n'.join(rows)+'\n');c.claim.chmod(0o600)
        p,_=c.cmd('retire',c.id)
        result(c.id,p.returncode!=0 and alive(c.pid) and alive(c.child) and not c.signals() and c.source.exists() and c.claim.exists(),cli_status=p.returncode,leader_alive=alive(c.pid),child_alive=alive(c.child),signals=c.signals(),registration_preserved=c.source.exists(),claim_preserved=c.claim.exists())
        c.claim.write_text('\n'.join(original)+'\n');c.claim.chmod(0o600)
    finally:c.cleanup()

log('Host: '+subprocess.check_output(['uname','-a'],text=True).strip())
log('Base: b84e0e362face25f3dd8945297a3df1320d7668c; target: '+subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
for version in ['base','target']:
    healthy(version); guard(version)
for action in ['retire','reconcile','sweep-home']:
    resistant(action)
    if action!='retire':healthy('target',action)
resistant('retire',zombie=True)
mismatch();crash()
(EVIDENCE/'live-results.json').write_text(json.dumps(RESULTS,indent=2)+'\n')
assert all(r['passed'] for r in RESULTS if not r['name'].startswith('base-'))
assert all(not r['passed'] for r in RESULTS if r['name'].startswith('base-'))
log('Both baseline failures reproduced; all target observations satisfied.')
