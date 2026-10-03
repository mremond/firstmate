from pathlib import Path
import subprocess,json,time,shlex
r=Path.cwd(); d=r/'.test-busy-lab'; e=Path('/Users/mremond/.no-mistakes/evidence/01M41JF8PZQEQWCHFEW097SGNE'); st=d/'home/state'; inbox=st/'pi-worker.inbox'; session=(d/'session').read_text().strip(); pane=json.loads((d/'pi-worker.json').read_text())['result']['root_pane']['pane_id']; win=session+':'+pane
rows=[]
def lab(*a): return subprocess.check_output([str(r/'bin/fm-herdr-lab.sh'),'run',session,*a],text=True)
def sh(code):
 p=subprocess.run(['bash','-c','. .test-busy-lab/env.sh; export FM_TASK_INBOX_GRACE_SECS=0; . bin/fm-watch.sh; '+code],text=True,capture_output=True)
 if p.returncode: raise RuntimeError(p.stdout+p.stderr)
 return p.stdout+p.stderr
def wait(state):
 for _ in range(100):
  if f'state={state} ' in (st/'pi-worker.busy-state').read_text(): return
  time.sleep(.5)
 raise RuntimeError('native hook never reached '+state)
def wake_count(rec): return sum(str(rec) in x for x in (st/'.wake-queue').read_text().splitlines())
def check(label):
 out=sh('inbox_steer_check '+shlex.quote(win)+' pi-worker'); row={'label':label,'output':out,'busy_budget':(inbox/'.busy-state').read_text() if (inbox/'.busy-state').is_file() else None,'ring_state':(inbox/'.ring-state').read_text() if (inbox/'.ring-state').is_file() else None};rows.append(row);print(json.dumps(row),flush=True);return row
def ack(n): (inbox/f'{n:03}.msg').rename(inbox/'handled'/f'{n:03}.msg')
def write(): return Path(sh('fm_task_inbox_write "$STATE" pi-worker "QA durable instruction: reply RECEIVED and do not read or acknowledge files."').strip())
def busy():
 lab('pane','send-text',pane,'Wait now: run exactly sleep 30, then reply WAIT_DONE. No other action.');lab('pane','send-keys',pane,'Enter');wait('busy')
wait('idle');ack(1);rec2=write();check('predecessor-idle-ring');assert (inbox/'.ring-state').read_text().startswith('002.msg\t1\t')
time.sleep(2);wait('idle');rec3=write();ack(2);busy()
check('successor-busy-1');assert wake_count(rec3)==0
check('successor-busy-2');assert wake_count(rec3)==1
check('successor-busy-3');check('successor-busy-4');assert wake_count(rec3)==1
assert (inbox/'.ring-state').read_text().startswith('002.msg\t1\t')
assert rec3.exists();print('PASS live successor deduplication with stale predecessor history',flush=True)
ack(3);rec4=write();check('reset-first-busy');assert wake_count(rec4)==0
wait('idle');lab('pane','send-text',pane,'QA_DRAFT_KEEP_6445');before=lab('pane','read',pane,'--source','visible')
check('reset-protected-nonbusy');after=lab('pane','read',pane,'--source','visible');(e/'pi-protected-draft.txt').write_text(after)
assert 'QA_DRAFT_KEEP_6445' in after;assert 'Firstmate instruction waiting' not in after.split('QA_DRAFT_KEEP_6445')[-1]
assert not (inbox/'.busy-state').exists();assert (inbox/'.ring-state').read_text().startswith('004.msg\t1\t')
lab('pane','send-keys',pane,'Enter');time.sleep(2);wait('idle');busy()
check('reset-new-busy-1');assert wake_count(rec4)==0
check('reset-new-busy-2');assert wake_count(rec4)==1
check('reset-new-busy-3');assert wake_count(rec4)==1
assert (inbox/'.ring-state').read_text().startswith('004.msg\t1\t');assert rec4.exists()
print('PASS live protected non-busy check resets streak and preserves attempt ladder',flush=True)
ack(4);rec5=write();(inbox/'.busy-state').unlink();(inbox/'.busy-state').mkdir();check('busy-bookkeeping-write-failure');assert wake_count(rec5)==1
check('busy-bookkeeping-write-failure-dedup');assert wake_count(rec5)==1
(inbox/'.busy-state').rmdir();ack(5);wait('idle');rec6=write();(inbox/'.busy-state').mkdir();check('busy-bookkeeping-reset-failure');assert 'cannot be reset after a non-busy check' in (st/'.wake-queue').read_text();assert rec6.exists();(inbox/'.busy-state').rmdir()
print('PASS live busy bookkeeping write and reset failures surface',flush=True)
(e/'pi-regressions-live.json').write_text(json.dumps(rows,indent=2)+'\n');(e/'pi-regressions-queue.tsv').write_text((st/'.wake-queue').read_text());(e/'pi-final-pane.txt').write_text(lab('pane','read',pane,'--source','recent','--lines','200'))
