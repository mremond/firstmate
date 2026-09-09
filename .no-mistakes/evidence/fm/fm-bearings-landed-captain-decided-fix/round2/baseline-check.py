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

h=LAB/'config-dangling';records=h/'records'
for f in [records/'backlog.md',h/'data/backlog.md']:
    run(['tasks-axi','update','duplicate-id','--title','Hold regression','--file',f],h,env_extra={'TASKS_AXI_BACKEND':'markdown'})
before=(h/'data/backlog.md').read_bytes(); configured_before=(records/'backlog.md').read_bytes()
p=run([ROOT/'bin/fm-captain-hold.sh','hold','duplicate-id','--title','Hold regression','--reason','Choose safely'],h,expect=1,env_extra={'FM_DATA_OVERRIDE':records},out='r2-target-refusal.txt')
assert 'cannot be read' in p.stderr
assert before==(h/'data/backlog.md').read_bytes() and configured_before==(records/'backlog.md').read_bytes()
p=run([ROOT/'.test-phase-r2/pre-r2/bin/fm-captain-hold.sh','hold','duplicate-id','--title','Hold regression','--reason','Choose safely'],h,env_extra={'FM_DATA_OVERRIDE':records},out='pre-r2-wrong-backlog.txt')
assert before!=(h/'data/backlog.md').read_bytes() and configured_before==(records/'backlog.md').read_bytes()
assert 'hold-kind: captain' in (h/'data/backlog.md').read_text()
(E/'pre-r2-default-backlog.md').write_bytes((h/'data/backlog.md').read_bytes())
base_landed={r['id']:r['artifact'] for r in json.loads((E/'baseline-bearings.json').read_text())['landed']}
assert base_landed.get('local-delivery')!='local main' and 'scout-empty' in base_landed
(E/'counterfactuals.json').write_text(json.dumps({'baseline_commit':'40c50ea8843c5b6a5351db8352675537252b653e','baseline_local_artifact':base_landed.get('local-delivery'),'baseline_reportless_scout_listed':True,'pre_r2_commit':'626bfa85','pre_r2_exit':p.returncode,'pre_r2_default_backlog_changed':True,'target_dangling_refused':True,'target_preserved_both_backlogs':True},indent=2)+'\n')
print('RED/GREEN confirmed: base loses cleanup-note artifact and includes reportless scout; pre-R2 changes the wrong backlog; target refuses and preserves both.')
