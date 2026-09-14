import json, os, signal, subprocess, time
from pathlib import Path

ROOT=Path.cwd()
EV=Path('/Users/mremond/.no-mistakes/evidence/01M2FG7SEEP1VBZ3B5SX35BJ6Q')
LAB=ROOT/'.test-phase/live-existing'
LAB.mkdir(parents=True,exist_ok=True)
BASH='/opt/homebrew/bin/bash'
results=[]
procs=[]
log=(EV/'live-existing-marker.log').open('w')
def say(msg):
 print(msg,flush=True); log.write(msg+'\n'); log.flush()
def wait_until(fn,secs=15):
 end=time.monotonic()+secs
 while time.monotonic()<end:
  if fn(): return
  time.sleep(.04)
 raise AssertionError('readiness condition timed out')
def fresh(name):
 home=LAB/name; state=home/'state'; state.mkdir(parents=True)
 for d in ['data','config','projects']: (home/d).mkdir()
 # Avoid unrelated detached summary work in the isolated empty home.
 (state/'home-summary.json').write_text('{}\n')
 (home/'config/backend').write_text('tmux\n')
 env=os.environ.copy()
 for key in list(env):
  if key.startswith('FM_') or key.startswith('TASKS_AXI_'): env.pop(key)
 env.update(FM_HOME=str(home),FM_STATE_OVERRIDE=str(state),FM_BACKEND='tmux',FM_POLL='.1',FM_SIGNAL_GRACE='0',FM_CHECK_INTERVAL='999999',FM_HEARTBEAT='999999',FM_TEST_SKIP_ORPHAN_REAP='1',FM_GATE_REFUSE_BYPASS='1',TMPDIR=str(ROOT/'.test-phase/tmp'))
 return home,state,env

def spawn(cmd,env,name):
 out=(EV/(name+'.out')).open('w'); err=(EV/(name+'.err')).open('w')
 p=subprocess.Popen(cmd,env=env,cwd=ROOT,stdout=out,stderr=err); procs.append(p)
 out.close(); err.close(); return p

def shell(code,env,args=(),timeout=15):
 r=subprocess.run([BASH,'-c',code,'_',str(ROOT/'bin/fm-wake-lib.sh'),*map(str,args)],env=env,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
 say('$ bash -c '+code.replace('\n',' '))
 if r.stdout: say(r.stdout.rstrip())
 if r.stderr: say(r.stderr.rstrip())
 say('exit='+str(r.returncode)); return r

def snapshot(pid):
 r=subprocess.run(['ps','-p',str(pid),'-o','pid=,ppid=,pgid=,stat=,args='],capture_output=True,text=True)
 return r.stdout.strip() or '(pid absent)'
def start(env,state,name):
 p=spawn([str(ROOT/'bin/fm-watch.sh')],env,name)
 wait_until(lambda: (state/'.last-watcher-beat').exists() and (state/'.watch.lock/pid').exists())
 assert (state/'.watch.lock/pid').read_text().strip()==str(p.pid)
 say(f'{name}: running watcher '+snapshot(p.pid)); return p

def terminate(p,name,limit=20):
 start=time.monotonic(); p.send_signal(signal.SIGTERM); rc=p.wait(timeout=limit); elapsed=time.monotonic()-start
 say(f'{name}: TERM -> exit={rc}, elapsed={elapsed:.3f}s; '+snapshot(p.pid))
 err=(EV/(name+'.err')).read_text()
 if err: say(err.strip())
 assert rc!=0
 return elapsed,err

def record(name,fn):
 say('\nSCENARIO '+name)
 try:
  fn(); results.append(dict(name=name,result='pass'))
 except Exception as ex:
  say('FAIL '+repr(ex)); results.append(dict(name=name,result='fail',error=repr(ex)))


def normal():
 _,state,env=fresh('normal-stop'); p=start(env,state,'normal-stop')
 terminate(p,'normal-stop')
 assert not (state/'.watch.lock').exists()
 marker=(state/'.watcher-down').read_text(); say('Persisted recovery marker:\n'+marker.strip())
 assert marker.startswith('pending:downtime:')


def held():
 home,state,env=fresh('held-marker')
 # Removed ambient knobs must not stretch the internal deadline.
 env.update(FM_RECOVERY_MARKER_LOCK_TIMEOUT='999',FM_WATCHER_SHUTDOWN_LOCK_SECS='999')
 p=start(env,state,'held-marker'); ready=home/'holder.ready'
 code='. "$1"; fm_lock_acquire_wait "$2" || exit; printf "%s\\n" "$BASHPID" > "$3"; sleep 60'
 holder=spawn([BASH,'-c',code,'_',str(ROOT/'bin/fm-wake-lib.sh'),str(state/'.watcher-down.lock'),str(ready)],env,'marker-holder')
 wait_until(ready.exists); hp=int(ready.read_text()); say('Live marker holder '+snapshot(hp))
 elapsed,err=terminate(p,'held-marker')
 assert elapsed<20 and 'within 5s' in err and f'held by pid {hp}' in err
 assert holder.poll() is None and (state/'.watcher-down.lock/pid').read_text().strip()==str(hp)
 assert (state/'.watch.lock/pid').read_text().strip()==str(p.pid)
 say(f'Preserved singleton owner={p.pid}; marker holder={hp} still running; ambient 999s values ignored.')
 holder.kill(); holder.wait()
 # Exercise actual next startup through abandoned locks and the durable recovery output.
 nextp=spawn([str(ROOT/'bin/fm-watch.sh')],env,'held-marker-restart')
 rc=nextp.wait(timeout=20); out=(EV/'held-marker-restart.out').read_text()
 say(f'Next watcher exit={rc}, stdout:\n{out.strip()}')
 assert 'check: rearm-resurface' in out and 'already running' not in out


def resource():
 assert os.getuid()!=0, 'must run as non-root to induce permission failure'
 _,state,env=fresh('resource-stop'); p=start(env,state,'resource-stop')
 wait_until(lambda: not os.path.lexists(state/'.watcher-down.lock'))
 state.chmod(0o555)
 try:
  r=shell('. "$1"; if fm_lock_owner_dir "$2"; then exit 10; fi; printf "owner-directory failure established uid=%s\\n" "$(id -u)"; if fm_lock_try_acquire "$2"; then rc=0; else rc=$?; fi; printf "acquire returned=%s\\n" "$rc"; exit "$rc"',env,[state/'.resource.lock'],timeout=5)
  assert r.returncode==1 and 'acquire returned=1' in r.stdout
  elapsed,err=terminate(p,'resource-stop')
  assert elapsed<20 and 'within 5s' in err and 'retaining stale lock evidence' in err
  assert (state/'.watch.lock/pid').read_text().strip()==str(p.pid)
  say('State mode=0555; owner creation really failed; acquisition returned; singleton PID evidence retained.')
 finally: state.chmod(0o755)


def abandoned():
 home,state,env=fresh('abandoned-steal'); lock=state/'.watch.lock'
 lock.mkdir(); (lock/'pid').write_text('99999999\n')
 ready=home/'removed.ready'
 # DEBUG is only a timing barrier: production removal and acquisition functions stay intact.
 code='''set -T
. "$1"
primary=$2
ready=$3
barrier='fm_lock_try_create "$lockdir" "$steal_owner"'
trap 'if [[ "$BASH_COMMAND" == "$barrier" && "$lockdir" == "$primary" ]]; then printf "%s\\n" "$BASHPID" > "$ready"; kill -STOP "$BASHPID"; fi' DEBUG
fm_lock_try_acquire "$primary"
'''
 stealer=spawn([BASH,'-c',code,'_',str(ROOT/'bin/fm-wake-lib.sh'),str(lock),str(ready)],env,'abandoned-stealer')
 wait_until(ready.exists)
 assert not os.path.lexists(lock) and (state/'.watch.lock.steal/pid').read_text().strip()==str(stealer.pid)
 say('Primary removed, before replacement: '+snapshot(stealer.pid)); say('Remaining .steal PID='+str(stealer.pid))
 stealer.kill(); stealer.wait(); say('Killed stealer: '+snapshot(stealer.pid))
 r=shell('. "$1"; if fm_lock_try_acquire "$2"; then printf "acquired primary=%s owner=%s self=%s\\n" "$2" "$(cat "$2/pid")" "$BASHPID"; fm_lock_release "$2"; else exit 1; fi',env,[lock])
 assert r.returncode==0 and 'acquired primary=' in r.stdout
 assert not os.path.lexists(state/'.watch.lock.steal')
 nextp=spawn([str(ROOT/'bin/fm-watch.sh')],env,'abandoned-restart'); rc=nextp.wait(timeout=20)
 out=(EV/'abandoned-restart.out').read_text(); say(f'Watcher startup after recovery exit={rc}:\n{out.strip()}')
 assert 'check: rearm-resurface' in out and 'already running' not in out


def descendant():
 home,state,env=fresh('returned-descendant')
 script=state/'custom.check.sh'
 script.write_text('''#!/usr/bin/env bash
perl -e '$SIG{TERM}="IGNORE"; open my $ready, ">", $ENV{FM_TEST_DESCENDANT_READY} or die $!; print {$ready} "ready\\n"; close $ready; select undef, undef, undef, 4; open my $sentinel, ">", $ENV{FM_TEST_DESCENDANT_SENTINEL} or die $!; print {$sentinel} "late\\n"; close $sentinel; select undef, undef, undef, 1' &
printf '%s\\n' "$!" > "$FM_TEST_DESCENDANT_PID"
while [ ! -s "$FM_TEST_DESCENDANT_READY" ]; do sleep 0.01; done
: > "$FM_TEST_DIRECT_DONE"
'''); script.chmod(0o700)
 env.update(FM_CHECK_FORCE_FALLBACK='1',FM_CHECK_TIMEOUT='10',FM_TEST_DESCENDANT_READY=str(home/'ready'),FM_TEST_DESCENDANT_SENTINEL=str(home/'sentinel'),FM_TEST_DESCENDANT_PID=str(home/'child.pid'),FM_TEST_DIRECT_DONE=str(home/'direct.done'))
 r=subprocess.run([str(ROOT/'bin/fm-check-register.sh'),'custom'],env=env,capture_output=True,text=True); say(r.stdout.strip()); assert r.returncode==0,r.stderr
 p=spawn([str(ROOT/'bin/fm-watch.sh')],env,'returned-descendant')
 wait_until(lambda: (home/'direct.done').exists() and (state/'.last-check').exists())
 child=int((home/'child.pid').read_text()); say('Direct check returned, recorded descendant: '+snapshot(child))
 terminate(p,'returned-descendant')
 child_row=snapshot(child); say('Descendant after watcher stop: '+child_row)
 if child_row!='(pid absent)': assert child_row.split()[3].startswith('Z')
 time.sleep(4.1)
 assert not (home/'sentinel').exists()
 assert not list(state.glob('.fm-custom-check.*'))
 say('Sentinel absent after its scheduled write time; private custom snapshots absent.')

def existing():
 home,state,env=fresh('existing-marker')
 r=shell('. "$1"; fm_recovery_marker_publish "$2" downtime',env,[state/'.watcher-down'])
 assert r.returncode==0
 rfd,wfd=os.pipe(); os.set_blocking(wfd,False)
 filler=0
 try:
  while True: filler+=os.write(wfd,b'.'*4096)
 except BlockingIOError: pass
 os.set_blocking(wfd,True)
 errfile=(EV/'existing-marker.err').open('w')
 p=subprocess.Popen([str(ROOT/'bin/fm-watch.sh')],env=env,stdout=wfd,stderr=errfile)
 procs.append(p); os.close(wfd); errfile.close()
 wait_until(lambda: (state/'.heartbeat-streak').exists())
 ready=home/'holder.ready'
 holder=spawn([BASH,'-c','. "$1"; fm_lock_acquire_wait "$2"; printf "%s\\n" "$BASHPID" > "$3"; sleep 60','_',str(ROOT/'bin/fm-wake-lib.sh'),str(state/'.watcher-down.lock'),str(ready)],env,'existing-marker-holder')
 wait_until(ready.exists); hp=int(ready.read_text()); before=(state/'.watcher-down').read_text()
 say('Recovery delivery paused on full stdout pipe; live marker holder='+str(hp)+'; marker='+before.strip())
 os.set_blocking(rfd,False); received=b''; began=time.monotonic()
 deadline=time.monotonic()+20
 while time.monotonic()<deadline:
  try:
   data=os.read(rfd,65536)
   if not data: break
   received+=data
  except BlockingIOError: pass
  time.sleep(.01)
 rc=p.wait(timeout=2); elapsed=time.monotonic()-began; os.close(rfd)
 output=received[filler:].decode(); err=(EV/'existing-marker.err').read_text()
 say('Delivered stdout: '+output.strip()); say(f'exit={rc}; cleanup elapsed={elapsed:.3f}s'); say(err.strip())
 assert 'check: rearm-resurface' in output and 'within 5s' in err and f'held by pid {hp}' in err
 assert elapsed<20 and (state/'.watch.lock/pid').read_text().strip()==str(p.pid)
 assert (state/'.watcher-down').read_text()==before and holder.poll() is None
 say('Existing announced recovery generation and stale singleton preserved; holder remains live.')
 holder.kill();holder.wait()
record('A delivered recovery wake also closes within the deadline while preserving its generation',existing)

def ordinary():
 home,state,env=fresh('ordinary-marker')
 env['FM_RECOVERY_MARKER_LOCK_TIMEOUT']='1'
 ready=home/'holder.ready'
 holder=spawn([BASH,'-c','. "$1"; fm_lock_acquire_wait "$2"; printf "%s\\n" "$BASHPID" > "$3"; while [ ! -e "$4" ]; do sleep .1; done; fm_lock_release "$2"','_',str(ROOT/'bin/fm-wake-lib.sh'),str(state/'.watcher-down.lock'),str(ready),str(home/'release')],env,'ordinary-holder')
 wait_until(ready.exists)
 pub=spawn([BASH,'-c','. "$1"; fm_recovery_marker_publish "$2" downtime; printf "published after holder released\\n"','_',str(ROOT/'bin/fm-wake-lib.sh'),str(state/'.watcher-down')],env,'ordinary-publisher')
 time.sleep(6.2)
 assert pub.poll() is None and not (state/'.watcher-down').exists()
 say('Ordinary marker publisher still waiting after 6.2s, despite ambient timeout=1.')
 (home/'release').touch(); holder.wait(timeout=5); rc=pub.wait(timeout=5)
 say((EV/'ordinary-publisher.out').read_text().strip()); say((state/'.watcher-down').read_text().strip())
 assert rc==0
 r=shell('. "$1"; fm_lock_try_acquire "$2"; first=$FM_LOCK_OWNER_DIR; fm_lock_try_acquire "$2"; printf "self-held reclaim first=%s next=%s pid=%s\\n" "$first" "$FM_LOCK_OWNER_DIR" "$(cat "$2/pid")"; fm_lock_release "$2"',env,[state/'.self.lock'])
 assert r.returncode==0 and 'self-held reclaim' in r.stdout
record('Ordinary publication remains blocking and interrupted same-process ownership can be reclaimed',ordinary)

for p in procs:
 if p.poll() is None: p.kill(); p.wait()
(EV/'live-existing-marker-results.json').write_text(json.dumps(results,indent=2)+'\n')
log.close()
raise SystemExit(any(r['result']=='fail' for r in results))
