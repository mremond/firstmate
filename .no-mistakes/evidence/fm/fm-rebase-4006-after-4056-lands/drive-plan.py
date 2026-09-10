import json,os,subprocess,shlex
from pathlib import Path
E=Path(__file__).parent
R='bin/fm-test-run.sh'
env=os.environ.copy(); env['TMPDIR']=str(Path.cwd()/'.test-phase-tmp')
log=(E/'plan-and-fresh-timing.log').open('w')
def run(cmd):
    log.write('$ '+shlex.join(cmd)+'\n');log.flush()
    p=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    out=''
    for line in p.stdout:
        out+=line; print(line,end='',flush=True);log.write(line);log.flush()
    rc=p.wait();log.write(f'EXIT_STATUS={rc}\n');log.flush()
    assert rc==0,(cmd,rc)
    return out
coverage=run([R,'--check-coverage'])
assert 'serial=157 serial_shards=5 serial_unhinted=0' in coverage
plan={}
for k in range(1,6):
    lane=f'portable-serial-{k}of5'
    plan[lane]=run([R,'--list','--lane',lane]).splitlines()
(E/'shard-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
all_scripts=[s for v in plan.values() for s in v]
assert len(all_scripts)==157 and len(set(all_scripts))==157
# A narrowly filtered real lane produces a fresh artifact through the public runner.
# Its suite contains one existing script. This is a producer/consumer smoke, not lane-performance evidence.
lane=next(k for k,v in plan.items() if 'tests/fm-backend-orca.test.sh' in v)
families=subprocess.check_output([R,'--list-families'],text=True).splitlines()
cmd=[R,'--lane',lane]
for f in families:
    if f!='orca':cmd+=['--exclude-family',f]
cmd+=['--json',str(E/'fresh-serial-timing.json')]
run(cmd)
doc=json.loads((E/'fresh-serial-timing.json').read_text())
assert [s['path'] for s in doc['scripts']]==['tests/fm-backend-orca.test.sh']
assert doc['summary']['failed']==0 and doc['summary']['skipped_gate']==0
run([R,'--check-shard-balance',str(E/'fresh-serial-timing.json')])
run([R,'--aggregate-json',str(E/'fresh-aggregate.json'),str(E/'fresh-serial-timing.json')])
log.close()
