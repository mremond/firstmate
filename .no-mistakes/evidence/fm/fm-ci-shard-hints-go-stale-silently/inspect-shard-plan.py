import concurrent.futures, subprocess, json, os
from pathlib import Path
E=Path('/Users/mremond/.no-mistakes/evidence/01M20P1RQF711N8XQS8YPKN43T')
env=os.environ.copy(); env['TMPDIR']=str(Path.cwd()/'.local-shard-validation/tmp')
lanes=[f'portable-serial-{n}of6' for n in range(1,7)]+['portable-serial']
def inspect(lane):
    args=['bin/fm-test-run.sh','--list','--lane',lane]
    r=subprocess.run(args,text=True,capture_output=True,env=env)
    assert r.returncode==0, (args,r.stderr)
    (E/(lane+'-selection.txt')).write_text('$ '+' '.join(args)+'\n'+r.stdout)
    return lane,r.stdout.splitlines()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as p: selections=dict(p.map(inspect,lanes))
(E/'shard-selections.json').write_text(json.dumps(selections,indent=2)+'\n')
combined=sum((selections[n] for n in lanes[:6]),[])
assert len(combined)==len(set(combined))==len(selections['portable-serial'])==152
assert set(combined)==set(selections['portable-serial'])
print(json.dumps({lane:len(paths) for lane,paths in selections.items()}),flush=True)
for args in [['--list','--lane','portable-serial-1of5'],['--list','--lane','portable-serial-7of6'],['--jobs','2','--lane','portable-serial-1of6']]:
    r=subprocess.run(['bin/fm-test-run.sh',*args],text=True,capture_output=True,env=env)
    with (E/'shard-refusals.txt').open('a') as out: out.write('$ bin/fm-test-run.sh '+' '.join(args)+'\n'+r.stdout+r.stderr+f'exit={r.returncode}\n\n')
    assert r.returncode==2
print('Outdated count, out-of-range shard, and same-machine serial concurrency all refused',flush=True)
