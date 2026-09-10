import copy, hashlib, json, os, re, shlex, subprocess
from pathlib import Path
ROOT=Path.cwd()
E=Path(__file__).parent
D=E/'inputs'
D.mkdir(exist_ok=True)
env=os.environ.copy()
env['TMPDIR']=str(ROOT/'.test-phase-tmp')
R='bin/fm-test-run.sh'
log=(E/'balance-cli.log').open('w')
results=[]
def drive(name,cmd,rc=0,contains=(),extra_env=None):
    e=env.copy(); e.update(extra_env or {})
    p=subprocess.run(cmd,cwd=ROOT,env=e,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    text='\nCASE: '+name+'\n$ '+shlex.join(cmd)+'\n'+p.stdout+f'EXIT_STATUS={p.returncode}\n'
    print(text,flush=True); log.write(text); log.flush()
    assert p.returncode==rc,(name,p.returncode,rc)
    for s in contains: assert s in p.stdout,(name,s)
    results.append({'case':name,'command':cmd,'exit':p.returncode,'output':p.stdout})
    return p.stdout

def artifact(name,lane,wall,rows):
    p=D/(name+'.json')
    p.write_text(json.dumps({'run_id':name,'selection':'lane='+lane,'started_at':'2026-09-10T00:00:00Z','finished_at':'2026-09-10T00:30:00Z','summary':{'total':len(rows),'failed':0,'skipped_gate':0,'duration_ms':wall},'scripts':[{'path':path,'family':'afk','duration_ms':ms,'exit':0,'gate_skip':False,'gate_skip_reason':''} for path,ms in rows]},indent=2)+'\n')
    return str(p)

def guard(name,files,rc=0,contains=()):
    before={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}
    out=drive(name,[R,'--check-shard-balance',*files],rc,contains)
    assert before=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files},'guard changed timing inputs'
    return out

# These are deliberately controlled CLI input documents, not real elapsed durations.
healthy=[artifact('healthy-'+str(k),f'portable-serial-{k}of5',wall,[('tests/fm-watch-triage.test.sh',min(wall,500000))]) for k,wall in enumerate([840000,800000,700000,750000,810000],1)]
guard('healthy five-shard lane',healthy,contains=('ok shards=5','@46.7% bound=30min'))
for name,wall,rc in [('one-ms-under',1295999,0),('exact-72-percent',1296000,0),('one-ms-over',1296001,1)]:
    a=artifact(name,'portable-serial-1of1',wall,[('tests/fm-watch-triage.test.sh',1200000)])
    guard(name,[a],rc,('bound=30min',) if rc==0 else ('shard balance guard failed','max 72%'))
for name,wall in [('stale-hints-73-percent',1320000),('stale-hints-93-percent',1680000)]:
    a=artifact(name,'portable-serial-1of5',wall,[('tests/fm-watch-triage.test.sh',1200000),('tests/fm-teardown.test.sh',120000)])
    guard(name,[a],1,('max 72%','tests/fm-watch-triage.test.sh measured 1200.0s hint 592.7s (+607.3s)','re-measure'))
a=artifact('wall-not-script-sum','portable-serial-1of1',1320000,[('tests/fm-watch-triage.test.sh',1000)])
guard('wall time decides despite tiny script sum',[a],1,('73.3%','max 72%'))
a=artifact('drift-alone-not-a-gate','portable-serial-1of1',840000,[('tests/fm-trace-context-lib.test.sh',830000)])
guard('hint drift alone does not add a second failure bound',[a],contains=('ok shards=1','46.7%'))
guard('missing artifacts are explicitly unchecked',healthy[:1],contains=('partial 1 of 5','the rest are unchecked','ok shards=1'))
a=artifact('previous-partition','portable-serial-1of2',1000,[('tests/fm-trace-context-lib.test.sh',900)])
guard('recorded partition owns completeness',[a],contains=('partial 1 of 2',))
a=artifact('foreign','portable-parallel-1',1000,[('tests/fm-trace-context-lib.test.sh',900)])
guard('foreign input fails loudly',[a],1,('Traceback','AttributeError'))
a=D/'malformed.json'; a.write_text('{broken JSON')
guard('malformed JSON fails loudly',[str(a)],1,('Traceback','JSONDecodeError'))
drive('missing input usage',[R,'--check-shard-balance'],2,('requires at least one timing JSON',))
workflow=json.loads(subprocess.check_output(['ruby','-ryaml','-rjson','-e','puts JSON.generate(YAML.load_file(ARGV[0]))','.github/workflows/ci.yml'],text=True))
job=workflow['jobs']['tests-portable-serial']
assert job['timeout-minutes']==30 and len(job['strategy']['matrix']['shard'])==5
steps=workflow['jobs']['tests-timing-aggregate']['steps']
step=next(s['run'] for s in steps if s.get('name')=='Check portable serial shard balance')
(E/'balance-workflow-step.sh').write_text(step)
(E/'workflow-contract.json').write_text(json.dumps({'timeout_minutes':job['timeout-minutes'],'shards':job['strategy']['matrix']['shard'],'aggregate_if':workflow['jobs']['tests-timing-aggregate']['if'],'guard_step':step},indent=2)+'\n')
for case,files,rc,text in [('healthy',healthy,0,'ok shards=5'),('partial',healthy[:1],0,'partial 1 of 5'),('empty',[],0,'shard balance unchecked'),('over-limit',[str(D/'stale-hints-73-percent.json')],1,'max 72%')]:
    tmp=E/('workflow-'+case)
    downloads=tmp/'fm-test-aggregate'; downloads.mkdir(parents=True,exist_ok=True)
    for k,f in enumerate(files,1): (downloads/f'fm-test-timing-portable-serial-{k}.json').write_bytes(Path(f).read_bytes())
    # The CI glob must exclude the valid parallel-lane artifact.
    (downloads/'fm-test-timing-portable-parallel-1.json').write_bytes((D/'foreign.json').read_bytes())
    drive('workflow '+case,['bash',str(E/'balance-workflow-step.sh')],rc,(text,),{'RUNNER_TEMP':str(tmp)})
(E/'balance-cli-results.json').write_text(json.dumps(results,indent=2)+'\n')
log.close()
