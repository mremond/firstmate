from pathlib import Path
import subprocess,json,datetime
root=Path.cwd(); evidence=Path('/Users/mremond/.no-mistakes/evidence/01M2082V2RRVRBS459RBJ4K0BY')
rows=[]
for line in subprocess.check_output(['ps','-axo','pid=,ppid=,pgid=,args='],text=True).splitlines():
 parts=line.strip().split(None,3)
 if len(parts)==4:rows.append(dict(pid=int(parts[0]),ppid=int(parts[1]),pgid=int(parts[2]),args=parts[3]))
scoped=[r for r in rows if str(root/'.test-phase/') in r['args'] and not r['args'].startswith('/bin/zsh -c')]
events=[json.loads(line) for line in (evidence/'live-teardown-probe.jsonl').read_text().splitlines()]
tracked={p['pid'] for e in events if e['event']=='armed' for p in e['polls']}
groups={p['pgid'] for e in events if e['event']=='armed' for p in e['polls']}
groups.add(14115)
tracked.update([49693,40604,14115])
remaining=[r for r in rows if r['pid'] in tracked or r['pgid'] in groups]
result=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),target='3cea357284a5419aeacb0ad823b6e48091a4f826',remaining_run_scoped_processes=scoped,remaining_recorded_pids_or_groups=remaining)
print(json.dumps(result,indent=2))
assert not scoped and not remaining
