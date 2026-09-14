from pathlib import Path
import subprocess,os,json,concurrent.futures
root=Path.cwd();home=root/'.test-lab/clock';(home/'projects').mkdir(exist_ok=True)
with (home/'state/clock.meta').open('a') as f:f.write(f'worktree={home}/projects\nwindow=bearings-validation:clock\n')
(home/'state/clock.status').write_text('paused: waiting on outside maintainer\n')
(home/'data/backlog.md').write_text('## In flight\n- [ ] clock - Concurrent delivery registration (repo: firstmate) (kind: ship) (since 2026-09-14)\n\n## Queued\n\n## Done\n')
env={**os.environ,'FM_HOME':str(home),'FM_STATE_OVERRIDE':str(home/'state'),'FM_DATA_OVERRIDE':str(home/'data')}
def writer():
 for i in range(12):
  url='https://github.com/kunchenguid/firstmate/pull/'+('4019' if i%2 else '4444')
  p=subprocess.run([str(root/'bin/fm-pr-check.sh'),'clock',url],env=env,capture_output=True,text=True);assert p.returncode==0,p.stderr
 return 12
def read():
 result=[]
 for _ in range(5):
  p=subprocess.run([str(root/'bin/fm-fleet-snapshot.sh'),'--json'],env=env,capture_output=True,text=True);assert p.returncode==0,p.stderr
  s=json.loads(p.stdout);t=next(t for t in s['tasks'] if t['id']=='clock');poll=t['pr']['merge_poll']
  assert not poll['armed'] or isinstance(poll['armed_epoch'],int),poll
  assert poll['armed'] or poll['armed_epoch'] is None,poll
  result.append(dict(generated=s['generated'],pr=t['pr']))
 return result
with concurrent.futures.ThreadPoolExecutor(2) as pool:
 w=pool.submit(writer);r=pool.submit(read);results=r.result();writes=w.result()
print(json.dumps(dict(registrations_replaced=writes,snapshots=results),indent=2))
