import collections, json, os, re, shlex, subprocess
from pathlib import Path
root=Path.cwd(); ev=Path('/Users/mremond/.no-mistakes/evidence/01M20TE28ZPPZJ712ASRP3J3S9')
env=dict(os.environ,TMPDIR=str(root/'.test-phase-tmp'))
ids=['34180535832','34167501605','34167485767','34156531229']
maxima={}; recorded={}; lines=[]; per_path_runs=collections.Counter()
for rid in ids:
    paths=sorted((ev/'source-runs'/rid).glob('fm-test-timing-portable-serial-*/*.json'))
    assert len(paths)==5,(rid,paths)
    records={}
    for path in paths:
        data=json.loads(path.read_text())
        assert data['summary']['failed']==0
        for script in data['scripts']:
            p=script['path']; value=script['duration_ms']
            assert p not in records,(rid,p)
            records[p]=value
            maxima[p]=max(maxima.get(p,0),value)
    recorded[rid]=records
    per_path_runs.update(records.keys())
    lines.append(f'Source {rid}: 5/5 serial artifacts, {len(records)} script paths, no script failure. All five serial jobs and overall CI verified completed/success using gh-axi run view.')
    cmd=['bin/fm-test-run.sh','--check-shard-balance',*[str(p) for p in paths]]
    p=subprocess.run(cmd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (ev/f'historical-guard-{rid}.txt').write_text('$ '+shlex.join(cmd)+'\n'+p.stdout+f'exit={p.returncode}\n')
    lines += [f'Current guard replay on original five-shard artifacts (recorded evidence, not live): exit={p.returncode}',p.stdout.rstrip()]
# This is the explicitly retained native-Windows measurement in the refresh contract.
maxima['tests/fm-pi-windows-shell-invocation.test.sh']=5121
assignments=json.loads((ev/'lane-selection.json').read_text())
serial=set(sum(assignments.values(),[]))
assert set(maxima)==serial,(len(maxima),sorted(set(maxima)^serial))
assert sum(maxima.values())==4974498,sum(maxima.values())
loads=[0]*6; expected=[[] for _ in range(6)]
for path,ms in sorted(maxima.items(),key=lambda item:(-item[1],item[0])):
    idx=min(range(6),key=loads.__getitem__)
    expected[idx].append(path); loads[idx]+=ms
for idx,(lane,paths) in enumerate(assignments.items()):
    assert set(expected[idx])==set(paths),lane
# The published table is the owned, reader-facing data contract, not an implementation proxy.
doc=root/'docs/fm-test-portable-shards.md'
rows=re.findall(r'^\| `(?P<lane>portable-serial-\d+of6)` \| (?P<count>\d+) \| (?P<weight>\d+) ms',doc.read_text(),re.M)
assert len(rows)==6
lines += ['','Retained maxima: 152 paths, 4,974,498 ms including the documented 5,121 ms Windows measurement.',f'Number of source runs per path: {dict(collections.Counter(per_path_runs.values()))}','Public --list --lane results exactly match longest-first packing of the source maxima:']
for lane,count,weight in rows:
    paths=assignments[lane]; observed_weight=sum(maxima[p] for p in paths)
    assert len(paths)==int(count) and observed_weight==int(weight),(lane,count,weight,observed_weight)
    lines.append(f'{lane}: {len(paths)} scripts, {observed_weight} ms; agrees with published table.')
lines += ['','Regrouped recorded durations under the actual six-shard selection (replay only):']
for rid,record in recorded.items():
    totals={lane:sum(record.get(p,0) for p in paths) for lane,paths in assignments.items()}
    worst=max(totals.values())
    lines.append(f'{rid}: worst shard={worst/60000:.2f} min ({worst/1200000*100:.2f}% of 20 min); {len(serial-set(record))} missing path(s) in this historical run.')
(ev/'measurements-check.txt').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
