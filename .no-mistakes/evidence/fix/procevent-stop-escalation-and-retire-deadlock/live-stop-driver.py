#!/usr/bin/env python3
"""Drive the real process-event CLI with isolated homes and real OS processes."""
import argparse, json, os, pathlib, shlex, shutil, signal, subprocess, time
p = argparse.ArgumentParser()
p.add_argument('code_root'); p.add_argument('runtime_root'); p.add_argument('scenarios', nargs='+')
a = p.parse_args()
root = pathlib.Path(a.code_root).absolute(); runtime = pathlib.Path(a.runtime_root).absolute()
runtime.mkdir(parents=True, exist_ok=True)
source = r'''
use strict; use warnings;
my ($dir, $resist, $disable) = @ARGV;
sub record { my ($file, $value) = @_; open my $f, '>>', "$dir/$file" or die $!; print $f "$value\n"; close $f; }
if ($resist) { $SIG{TERM} = sub { chmod 0, $disable if length($disable // ""); record('signals', "TERM $$"); }; $SIG{INT} = 'IGNORE'; $SIG{HUP} = 'IGNORE'; }
my $child = fork; defined $child or die $!;
if (!$child) { record('descendant', $$); my $end = time + 120; while (time < $end) { select undef, undef, undef, 0.1; } exit; }
record('child', $$);
my $end = time + 120; while (time < $end) { select undef, undef, undef, 0.1; }
'''
zombie_parent = r'''
my $release = shift @ARGV;
defined(my $pid = fork) or exit 125;
if (!$pid) { setpgrp(0,0) or exit 125; $ENV{FM_PROCEVENT_RUNNER_GROUP} = $$; exec @ARGV; exit 125; }
my $end = time + 120; while (!-e $release && time < $end) { select undef,undef,undef,0.05; }
waitpid($pid,0); exit 0;
'''
def alive(pid):
    try: os.kill(pid, 0); return True
    except (ProcessLookupError, PermissionError): return False

def wait_until(fn, timeout=35):
    end = time.monotonic()+timeout
    while time.monotonic()<end:
        if fn(): return True
        time.sleep(.05)
    return bool(fn())

def group(pid):
    rows = subprocess.run(['/bin/ps','-Ao','pid=,ppid=,pgid=,stat=,comm='],capture_output=True,text=True,check=True).stdout.splitlines()
    return [x.strip() for x in rows if len(x.split())>=4 and x.split()[2]==str(pid)]

results=[]
for scenario in a.scenarios:
    home=runtime/scenario; (home/'state').mkdir(parents=True,exist_ok=True)
    claims=home/'claims'; claims.mkdir(exist_ok=True)
    env=os.environ.copy()
    for key in ['FM_STATE_OVERRIDE','FM_PROCEVENT_IN_RUNNER','FM_PROC_ROOT_OVERRIDE','FM_PROCEVENT_RUNNER_GROUP']:
        env.pop(key,None)
    env.update(FM_HOME=str(home), FM_PROCEVENT_CLAIM_ROOT=str(claims), FM_GATE_REFUSE_BYPASS='1', TMPDIR=str(home), FM_PROCEVENT_OWNER_LEASE_SECONDS=('5' if scenario=='guard' else '600'), FM_PROCEVENT_OWNER_CHECK_SECONDS=('1' if scenario=='guard' else '15'))
    local_ps=None
    if scenario.startswith('unreadable-'):
        toolbin=home/'tools'; toolbin.mkdir(exist_ok=True)
        for folder in ['/bin','/usr/bin','/usr/sbin']:
            for path in pathlib.Path(folder).iterdir():
                if path.name!='ps' and path.is_file() and not (toolbin/path.name).exists():
                    (toolbin/path.name).symlink_to(path)
        local_ps=toolbin/'ps'; shutil.copy('/bin/ps',local_ps)
        env['PATH']=str(toolbin); env['FM_PROC_ROOT_OVERRIDE']=str(home/'missing-proc')
    cli=str(root/'bin/fm-procevent.sh'); id='live-'+scenario
    runner=None; start=None; sf=None
    evidence={'scenario':scenario,'code_root':str(root),'home':str(home),'lease_seconds':env['FM_PROCEVENT_OWNER_LEASE_SECONDS'],'check_seconds':env['FM_PROCEVENT_OWNER_CHECK_SECONDS'],'commands':[]}
    def cmd(*args):
        before=time.monotonic()
        r=subprocess.run([cli,*args],env=env,capture_output=True,text=True,timeout=45)
        entry={'argv':list(args),'exit':r.returncode,'seconds':round(time.monotonic()-before,3),'stdout':r.stdout.strip(),'stderr':r.stderr.strip()}
        evidence['commands'].append(entry); print(json.dumps(entry),flush=True)
        return r
    def pending(*args):
        evidence['commands'].append({'argv':list(args),'mode':'background'})
        return subprocess.Popen([cli,*args],env=env,stdout=sf,stderr=subprocess.STDOUT)
    print('\nSCENARIO '+scenario,flush=True)
    try:
        resist=scenario!='healthy'
        source_path=home/'source.pl'; source_path.write_text(source)
        assert cmd('register','lavish',id,'--','/usr/bin/perl',str(source_path),str(home),str(int(resist)),str(local_ps) if scenario=='unreadable-proved' else '').returncode==0
        sf=open(home/'start.log','w')
        if scenario in ['guard','crash']:
            assert cmd('reconcile').returncode==0
        elif scenario=='zombie':
            evidence['commands'].append({'argv':['_start',id],'mode':'real child with parent delaying waitpid'})
            start=subprocess.Popen(['/usr/bin/perl','-e',zombie_parent,str(home/'release'),cli,'_start',id],env=env,stdout=sf,stderr=subprocess.STDOUT)
        else: start=pending('start',id)
        claim=claims/(id+'.claim')
        ready=lambda: claim.exists() and (home/'child').exists() and (home/'descendant').exists()
        if scenario=='guard':
            end=time.monotonic()+90
            while not ready() and time.monotonic()<end:
                cmd('reconcile')
                time.sleep(.1)
        assert wait_until(ready), 'startup incomplete'
        original=claim.read_text(); lines=original.splitlines(); runner=int(lines[1])
        child=int((home/'child').read_text().strip()); descendant=int((home/'descendant').read_text().strip())
        # The list command crosses startup's actual source-lock boundary.
        assert cmd('list').returncode==0
        evidence.update(runner=runner,child=child,descendant=descendant,before=group(runner))
        print('before='+json.dumps(evidence['before']),flush=True)
        if scenario=='healthy':
            r=cmd('retire',id); status=start.wait(timeout=20)
            evidence['start_exit']=status
            evidence['group_gone']=wait_until(lambda:not alive(-runner))
            assert r.returncode==0 and status==143 and evidence['group_gone'], 'healthy stop must exit 143 on TERM'
        elif scenario in ['retire','zombie']:
            with open(home/'retire.log','w') as rf:
                began=time.monotonic(); stopper=subprocess.Popen([cli,'retire',id],env=env,stdout=rf,stderr=subprocess.STDOUT)
                evidence['commands'].append({'argv':['retire',id],'mode':'background to observe transition'})
                def transitioned():
                    if scenario=='zombie':
                        return subprocess.run(['/bin/ps','-o','stat=','-p',str(runner)],capture_output=True,text=True).stdout.strip().startswith('Z')
                    return not alive(runner)
                evidence['leader_transition']=wait_until(transitioned,45)
                evidence['child_survived_term']=alive(child)
                evidence['transition_group']=group(runner)
                print('after TERM='+json.dumps(evidence['transition_group']),flush=True)
                evidence['child_reaped']=wait_until(lambda:not alive(child),12)
                (home/'release').touch()
                rc=stopper.wait(timeout=20)
                evidence['retire_exit']=rc; evidence['retire_seconds']=round(time.monotonic()-began,3); evidence['retire_output']=(home/'retire.log').read_text()
                assert evidence['leader_transition'] and evidence['child_survived_term'] and evidence['child_reaped'] and rc==0, 'escalation abandoned group'
                if start: start.wait(timeout=20)
                assert wait_until(lambda:not alive(-runner)), 'group remains'
        elif scenario=='guard':
            assert cmd('reconcile').returncode==0
            began=time.monotonic(); nominal=5+2*1+4
            evidence['nominal_bound_seconds']=nominal; evidence['loaded_deadline_seconds']=2*nominal
            evidence['group_gone']=wait_until(lambda:not alive(-runner),2*nominal)
            evidence['elapsed_seconds']=round(time.monotonic()-began,3)
            assert evidence['group_gone'], 'guard exceeded lease + two checks + stop grace, with 2x scheduling allowance'
        elif scenario=='crash':
            rows=subprocess.run(['/bin/ps','-Ao','pid=,command='],capture_output=True,text=True,check=True).stdout.splitlines()
            matching=[row for row in rows if f'_owner-watchdog {id} {runner} ' in row and cli in row]
            assert len(matching)==1, 'could not identify this runner guard'
            guard_pid=int(matching[0].split()[0]); evidence['guard_pid']=guard_pid
            os.kill(runner,signal.SIGKILL)
            assert wait_until(lambda:not alive(runner)), 'leader did not die'
            assert alive(-runner), 'group did not survive independent death'
            evidence['after_crash']=group(runner)
            for op in [('retire',id),('reconcile',),('sweep-home',)]:
                r=cmd(*op)
                if op[0]!='reconcile': assert r.returncode!=0, 'unproved group accepted'
                assert alive(child) and alive(descendant) and claim.exists(), 'unproved group signalled or claim lost'
            evidence['guard_exited_without_signal']=wait_until(lambda:not alive(guard_pid),40)
            assert evidence['guard_exited_without_signal'], 'guard did not observe independently crashed leader'
            assert alive(child) and alive(descendant), 'guard signalled unproved group'
            assert not (home/'signals').exists(), 'unproved group received TERM'
            assert (home/'state/procevent'/f'{id}.source').exists(), 'registration lost'
        elif scenario.startswith('unreadable-'):
            if scenario=='unreadable-cold': local_ps.chmod(0)
            else: os.kill(runner,signal.SIGSTOP)
            r=cmd('retire',id)
            try:
                subprocess.run([str(local_ps),'-p',str(runner),'-o','lstart='],check=True,capture_output=True)
                raise AssertionError('ps execution unexpectedly available')
            except PermissionError as error:
                evidence['real_ps_failure']=str(error)
            if scenario=='unreadable-cold':
                assert r.returncode!=0 and alive(runner) and alive(child) and not (home/'signals').exists(), 'unproved unreadable group signalled'
                assert claim.exists() and (home/'state/procevent'/f'{id}.source').exists(), 'refusal lost retry state'
            else:
                assert r.returncode==0 and wait_until(lambda:not alive(-runner)), 'proved group abandoned after actual ps permission loss'
                assert (home/'signals').exists(), 'child did not receive TERM'
                assert not claim.exists() and not (home/'state/procevent'/f'{id}.source').exists(), 'proved stop left claim or registration'
            local_ps.chmod(0o755)
        elif scenario in ['mismatch','nonleader']:
            if scenario=='mismatch': lines[3]='deliberately wrong recorded identity'
            else:
                lines[1]=str(child)
                identity=subprocess.run(['/bin/bash','-c','. "$1/bin/fm-wake-lib.sh"; fm_pid_identity "$2"','_',str(root),str(child)],env=env,capture_output=True,text=True,check=True).stdout.strip()
                lines[3]=identity
            claim.write_text('\n'.join(lines)+'\n')
            r=cmd('retire',id)
            assert r.returncode!=0 and 'cannot confirm runner identity' in r.stderr+r.stdout, 'unsafe first signal accepted'
            assert alive(child) and alive(runner) and not (home/'signals').exists(), 'refusal signalled live group'
            assert claim.exists() and (home/'state/procevent'/f'{id}.source').exists(), 'refusal lost retry state'
            claim.write_text(original)
        evidence['signals']=(home/'signals').read_text() if (home/'signals').exists() else ''
        if resist and scenario in ['retire','zombie','guard']: assert evidence['signals'], 'never received TERM'
        evidence['after']=group(runner)
        evidence['result']='pass'
    except Exception as e:
        evidence['result']='fail'; evidence['error']=str(e)
        if runner: evidence['after']=group(runner)
    finally:
        if runner and alive(-runner):
            evidence['cleanup']='test-owned group SIGKILL'
            os.killpg(runner,signal.SIGKILL)
        (home/'release').touch()
        if start:
            try: start.wait(timeout=15)
            except subprocess.TimeoutExpired: start.kill(); start.wait()
        if sf: sf.close()
        if local_ps: local_ps.chmod(0o755)
        if runner: wait_until(lambda:not alive(-runner),10)
        try: cmd('retire',id)
        except Exception as e: evidence['cleanup_error']=str(e)
        print('RESULT '+json.dumps(evidence),flush=True)
        results.append(evidence)
print('\nFINAL '+json.dumps(results),flush=True)
raise SystemExit(1 if any(x['result']=='fail' for x in results) else 0)
