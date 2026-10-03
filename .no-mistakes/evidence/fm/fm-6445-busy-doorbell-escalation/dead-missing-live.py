from pathlib import Path
import subprocess,json,shlex
r=Path.cwd();d=r/'.test-busy-lab';e=Path('/Users/mremond/.no-mistakes/evidence/01M41JF8PZQEQWCHFEW097SGNE');st=d/'home/state';ib=st/'pi-worker.inbox';s=(d/'session').read_text().strip();pane=json.loads((d/'pi-worker.json').read_text())['result']['root_pane']['pane_id'];w=s+':'+pane

def run(code):
 p=subprocess.run(['bash','-c','. .test-busy-lab/env.sh; export FM_TASK_INBOX_GRACE_SECS=0; . bin/fm-watch.sh; '+code],text=True,capture_output=True);assert p.returncode==0,(p.stdout,p.stderr);return p.stdout+p.stderr
for mode,prev in [('dead',7),('missing',8)]:
 (ib/f'{prev:03}.msg').rename(ib/'handled'/f'{prev:03}.msg')
 rec=run('fm_task_inbox_write "$STATE" pi-worker "QA successor after endpoint loss."').strip()
 if mode=='missing': subprocess.run([str(r/'bin/fm-herdr-lab.sh'),'run',s,'pane','close',pane],check=True,capture_output=True)
 assert run('fm_backend_agent_state herdr '+shlex.quote(w)).strip()==mode
 for n in range(1,5):
  out=run('inbox_steer_check '+shlex.quote(w)+' pi-worker');q=(st/'.wake-queue').read_text();count=sum(rec in x for x in q.splitlines());print(json.dumps({'mode':mode,'check':n,'output':out,'wakes':count}),flush=True);assert count==1
 assert (ib/'.ring-state').read_text().startswith('004.msg\t1\t')
(e/'dead-missing-queue.tsv').write_text((st/'.wake-queue').read_text())
