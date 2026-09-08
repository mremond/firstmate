import json, re, subprocess, os
from pathlib import Path
E=Path('/Users/mremond/.no-mistakes/evidence/01M20P1RQF711N8XQS8YPKN43T')
selections=json.loads((E/'shard-selections.json').read_text())
maxima={}; sources={}; raw_runs={}
for run in sorted((E/'source-runs').iterdir()):
    files=sorted(run.glob('fm-test-timing-portable-serial-*/*.json'))
    assert len(files)==5
    measurements={}
    for file in files:
        data=json.loads(file.read_text())
        assert data['summary']['failed']==0
        for script in data['scripts']:
            p=script['path']; ms=script['duration_ms']
            assert p not in measurements
            measurements[p]=ms
            if ms>maxima.get(p,-1): maxima[p]=ms; sources[p]=run.name
    raw_runs[run.name]=measurements
native='tests/fm-pi-windows-shell-invocation.test.sh'
native_ci_max=maxima[native]
maxima[native]=5121
sources[native]='Documented native Windows measurement (not re-run on this macOS host)'
assert set(selections['portable-serial'])==set(maxima)
loads=[0]*6; expected=[[] for _ in range(6)]
for path in sorted(maxima,key=lambda p:(-maxima[p],p)):
    target=min(range(6),key=lambda i:loads[i])
    expected[target].append(path); loads[target]+=maxima[path]
rows=[]
for i,paths in enumerate(expected):
    lane=f'portable-serial-{i+1}of6'
    assert set(paths)==set(selections[lane]),lane
    rows.append({'lane':lane,'scripts':len(paths),'weight_ms':loads[i]})
doc=Path('docs/fm-test-portable-shards.md').read_text()
for row in rows:
    match=re.search(r'\| `'+row['lane']+r'` \| (\d+) \| (\d+) ms',doc)
    assert match and [int(x) for x in match.groups()]==[row['scripts'],row['weight_ms']],row
actual=[]
for run,measurements in raw_runs.items():
    sums=[sum(measurements.get(p,0) for p in paths) for paths in expected]
    actual.append({'run':run,'per_shard_script_sum_ms':sums,'worst_minutes':max(sums)/60000,'worst_cap_percent':max(sums)/12000})
report={'target':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'source_runs':list(raw_runs),'source_artifacts':20,'ci_maxima_paths':len(maxima),'native_windows_override_ms':5121,'native_windows_max_ci_skip_ms':native_ci_max,'native_windows_limitation':'Retained documented pre-existing measurement; not independently re-measured on macOS.','weight_total_ms':sum(loads),'imbalance_ms':max(loads)-min(loads),'shards':rows,'repacked_source_run_durations':actual,'result':'All six runtime CLI memberships match a packing from measured per-path maxima; all six documentation rows match those memberships and weights.'}
(E/'measured-plan-verification.json').write_text(json.dumps(report,indent=2)+'\n')
(E/'measured-path-maxima.json').write_text(json.dumps({p:{'duration_ms':maxima[p],'source':sources[p]} for p in sorted(maxima)},indent=2)+'\n')
print(json.dumps(report,indent=2))
env=os.environ.copy();env['TMPDIR']=str(Path.cwd()/'.local-shard-validation/tmp')
with (E/'historical-guard-replay.txt').open('w') as out:
    for run in raw_runs:
        args=['bin/fm-test-run.sh','--check-shard-balance',*map(str,sorted((E/'source-runs'/run).glob('fm-test-timing-portable-serial-*/*.json')))]
        r=subprocess.run(args,capture_output=True,text=True,env=env)
        out.write(f'Historical artifact replay, source CI run {run}:\n'+r.stdout+r.stderr+f'exit={r.returncode}\n\n')
        assert r.returncode==1,(run,r.stdout,r.stderr)
print('All four archived five-shard runs trigger the new headroom check before their 20-minute cap.')
