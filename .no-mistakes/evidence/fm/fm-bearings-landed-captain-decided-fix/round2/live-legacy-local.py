from pathlib import Path
import os, subprocess, json, shlex, shutil, hashlib
ROOT=Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22J3ZVNCRVXG5Q4HD5QXABZ')
E=Path('/Users/mremond/.no-mistakes/evidence/01M22J3ZVNCRVXG5Q4HD5QXABZ/round2')
LAB=ROOT/'.test-phase-r2/live'
LAB.mkdir(parents=True,exist_ok=True)
if not (E/'live-cli-transcript.txt').exists(): (E/'live-cli-transcript.txt').write_text('Real Firstmate CLI checks; isolated data, real tasks-axi 0.2.5 and Git; no external-command stubs.\n')
results=[]
def log(s):
    with (E/'live-cli-transcript.txt').open('a') as f: f.write(s+'\n')
def run(args, home=None, expect=0, env_extra=None, out=None, cwd=None):
    args=[str(x) for x in args]
    env=os.environ.copy()
    for k in list(env):
        if k.startswith(('FM_','TASKS_AXI_')) or k in ('TMUX','GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE'): env.pop(k,None)
    if home:
        env.update(FM_HOME=str(home),FM_ROOT_OVERRIDE=str(LAB/'code-root'),FM_STATE_OVERRIDE=str(home/'state'),FM_DATA_OVERRIDE=str(home/'data'),FM_CONFIG_OVERRIDE=str(home/'config'),FM_PROJECTS_OVERRIDE=str(home/'projects'),HOME=str(LAB/'user-home'),TMPDIR=str(ROOT/'.test-phase-r2/tmp'),TMUX_TMPDIR=str(ROOT/'.test-phase-r2/tmp'),FM_GATE_REFUSE_BYPASS='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_AUTHOR_NAME='Firstmate Validation',GIT_AUTHOR_EMAIL='test@example.invalid',GIT_COMMITTER_NAME='Firstmate Validation',GIT_COMMITTER_EMAIL='test@example.invalid')
    if env_extra: env.update({k:str(v) for k,v in env_extra.items()})
    p=subprocess.run(args,cwd=cwd or home or ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
    log('$ '+shlex.join(args)+'\n'+('FM_HOME='+str(home)+'\n' if home else '')+'exit='+str(p.returncode)+'\n'+p.stdout+p.stderr)
    if out: (E/out).write_text(p.stdout)
    if expect is not None: assert p.returncode==expect, (args,p.returncode,p.stdout,p.stderr)
    return p

def make_home(name):
    h=LAB/name
    for d in ['data','state','config','projects']: (h/d).mkdir(parents=True,exist_ok=True)
    (h/'state').chmod(0o700)
    (h/'.tasks.toml').write_text('backend = "markdown"\n[markdown]\npath = "data/backlog.md"\narchive = "data/done-archive.md"\ndone_keep = 100\n')
    (h/'data/backlog.md').write_text('## In flight\n\n## Queued\n\n## Done\n')
    return h

def tasks(h,*args): return run(['tasks-axi',*args],h)
def hold(h,id): return run([ROOT/'bin/fm-captain-hold.sh','hold',id,'--reason','Review this isolated validation task'],h)
def answer(h,id,release=False,words='Choose the documented option.'):
    f=h/(id+'-answer.txt');f.write_text(words+'\n')
    return run([ROOT/'bin/fm-captain-hold.sh','answer',id,'--decision-file',f,*(['--release'] if release else [])],h)
def snapshot(h,name):
    p=run([ROOT/'bin/fm-bearings-snapshot.sh','--json','--all-landed'],h,out=name+'.json')
    run([ROOT/'bin/fm-bearings-snapshot.sh','--all-landed'],h,out=name+'.toon')
    return json.loads(p.stdout)
def passed(name,evidence):
    results.append(dict(name=name,result='pass',live=True,evidence=evidence,reason=''))
    (E/'live-results.json').write_text(json.dumps(results,indent=2)+'\n')
    log('ASSERTED: '+name)

results=json.loads((E/'live-results.json').read_text())
parent=make_home('legacy-parent');peer=make_home('legacy-peer')
(peer/'AGENTS.md').write_text('# Isolated Firstmate home\n')
(peer/'bin').mkdir();(peer/'.fm-secondmate-home').write_text('legacy-peer\n')
report=peer/'data/legacy-report/report.md';report.parent.mkdir();report.write_text('# Legacy report\n\nObserved real local delivery.\n')
tasks(peer,'add','legacy-report','Inspect legacy delivery','--kind','scout','--start')
tasks(peer,'done','legacy-report','--report','data/legacy-report/report.md')
p=run([ROOT/'.test-phase-r2/base/bin/fm-fleet-snapshot.sh','--secondmate-home-summary'],peer,out='legacy-producer-summary.json')
legacy=json.loads(p.stdout)
assert legacy['schema']=='fm-secondmate-home-summary.v1'
assert legacy['landed'][0]['report_path']=='data/legacy-report/report.md' and 'kind' not in legacy['landed'][0]
(peer/'state/home-summary.json').write_text(p.stdout)
(parent/'data/secondmates.md').write_text(f'# Secondmates\n\n- legacy-peer - Legacy producer compatibility (home: {peer}; scope: validation; projects: sample; added 2026-09-09)\n')
d=snapshot(parent,'legacy-live-local')
assert any(r['id']=='legacy-report' and r['artifact']=='data/legacy-report/report.md' and r['owner']=='legacy-peer' for r in d['landed']),d
passed('Reading a local v1 summary produced by the base version preserves its report artifact despite omitted kind','legacy-producer-summary.json; legacy-live-local.toon')
run([ROOT/'bin/fm-remote-doctor.sh'],peer,expect=None,out='isolated-remote-readiness.txt')
base=json.loads(run([ROOT/'.test-phase-r2/base/bin/fm-bearings-snapshot.sh','--json','--all-landed'],LAB/'main',out='baseline-bearings.json').stdout)
base_landed={r['id']:r['artifact'] for r in base['landed']}
assert base_landed.get('local-delivery')!='local main' and 'scout-empty' in base_landed
print('Legacy report preserved by target; baseline still loses local note and includes reportless scout.')
