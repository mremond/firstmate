from pathlib import Path
import os, subprocess, json, shlex, shutil, hashlib
ROOT=Path('/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M22J3ZVNCRVXG5Q4HD5QXABZ')
E=Path('/Users/mremond/.no-mistakes/evidence/01M22J3ZVNCRVXG5Q4HD5QXABZ')
LAB=ROOT/'.test-local/live'
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
        env.update(FM_HOME=str(home),FM_ROOT_OVERRIDE=str(LAB/'code-root'),FM_STATE_OVERRIDE=str(home/'state'),FM_DATA_OVERRIDE=str(home/'data'),FM_CONFIG_OVERRIDE=str(home/'config'),FM_PROJECTS_OVERRIDE=str(home/'projects'),HOME=str(LAB/'user-home'),TMPDIR=str(ROOT/'.test-local/tmp'),TMUX_TMPDIR=str(ROOT/'.test-local/tmp'),FM_GATE_REFUSE_BYPASS='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_AUTHOR_NAME='Firstmate Validation',GIT_AUTHOR_EMAIL='test@example.invalid',GIT_COMMITTER_NAME='Firstmate Validation',GIT_COMMITTER_EMAIL='test@example.invalid')
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
main=LAB/'main'
proj=main/'projects/local-project'
id='retained-report'
tasks(main,'add',id,'Inspect the recorded delivery','--kind','scout','--start')
report=main/'data'/id/'report.md';report.parent.mkdir();report.write_text('# Delivered report\n\nThe locally delivered file exists in the default branch.\n')
meta=main/'state'/f'{id}.meta'
meta.write_text(f'window=firstmate:fm-{id}\nworktree={main}/projects/retired-scout-copy\nproject={proj}\nkind=scout\nharness=codex\nmode=scout\nspawn_gen=live-retained-report\n')
meta.chmod(0o600)
hold(main,id)
run([ROOT/'bin/fm-captain-hold.sh','complete',id,id],main)
run([ROOT/'bin/fm-teardown.sh',id],main,out='held-scout-cleanup.txt')
show=tasks(main,'show',id,'--full').stdout
assert 'state: queued' in show and 'hold_kind: captain' in show and f'data/{id}/report.md' in show
assert not meta.exists()
(E/'held-scout-before-answer.txt').write_text(show)
answer(main,id,words='Retain the report and accept its conclusion.')
jsonout=snapshot(main,'retained-report-final')
assert any(r['id']==id and r['artifact']==f'data/{id}/report.md' for r in jsonout['landed'])
passed('Cleaning up a completed scout retains its unanswered captain call; answering later preserves its report in Recently Landed','held-scout-cleanup.txt; held-scout-before-answer.txt; retained-report-final.toon')

id='held-local';wt=main/'projects/held-local-copy'
run(['git','-C',proj,'worktree','add','-q','-b',f'fm/{id}',wt],main)
(wt/'held.txt').write_text('Delivery requiring release.\n')
run(['git','-C',wt,'add','held.txt'],main);run(['git','-C',wt,'commit','-qm','Held local delivery'],main)
tasks(main,'add',id,'Deliver after approval','--kind','ship','--start')
meta=main/'state'/f'{id}.meta'
meta.write_text(f'window=firstmate:fm-{id}\nworktree={wt}\nproject={proj}\nkind=ship\nharness=codex\nmode=local-only\nspawn_gen=live-held-local\n');meta.chmod(0o600)
hold(main,id)
sha=run(['git','-C',proj,'rev-parse','main'],main).stdout.strip()
p=run([ROOT/'bin/fm-merge-local.sh',id],main,expect=1,out='held-local-refusal.txt')
assert 'still held for the captain' in p.stderr
assert run(['git','-C',proj,'rev-parse','main'],main).stdout.strip()==sha
answer(main,id,True,words='Approve this isolated local delivery.')
run([ROOT/'bin/fm-merge-local.sh',id],main,out='released-local-merge.txt')
assert (proj/'held.txt').read_text()=='Delivery requiring release.\n'
passed('Attempting a local merge while captain-held preserves main; releasing the same task allows the fast-forward','held-local-refusal.txt; released-local-merge.txt; live-cli-transcript.txt')

for script,args in [('fm-merge-local.sh',['bad/id']),('fm-pr-merge.sh',['bad/id','https://github.com/kunchenguid/firstmate/pull/4048'])]:
    p=run([ROOT/'bin'/script,*args],main,expect=2)
missing=LAB/'missing-state-home';missing.mkdir()
for script,args in [('fm-merge-local.sh',['missing']),('fm-pr-merge.sh',['missing','https://github.com/kunchenguid/firstmate/pull/4048'])]:
    p=run([ROOT/'bin'/script,*args],missing,expect=1)
    assert 'state directory' in p.stderr
h=make_home('authority-read')
run([ROOT/'bin/fm-captain-hold.sh','open','absent','--distinguish-absent'],h,expect=3)
(h/'data/backlog.md').chmod(0)
run([ROOT/'bin/fm-captain-hold.sh','open','absent','--distinguish-absent'],h,expect=2)
(h/'data/backlog.md').chmod(0o600)
passed('Merge entrypoints reject malformed IDs and missing state promptly; captain-call reads distinguish absent tasks from unreadable records','live-cli-transcript.txt')

# Execute the original producer on the same real state: the old display picks
# no artifact for the completed cleanup-note local delivery.
base=json.loads(run([ROOT/'.test-local/base/bin/fm-bearings-snapshot.sh','--json','--all-landed'],main,out='baseline-bearings.json').stdout)
base_landed={r['id']:r['artifact'] for r in base['landed']}
assert base_landed.get('local-delivery') != 'local main'
assert 'scout-empty' in base_landed
# Regression R2: on the immediate pre-fix executable the same broken config
# silently switches from the relocated store to the default store.
h=LAB/'config-dangling'; records=h/'records'
before=(h/'data/backlog.md').read_bytes()
p=run([ROOT/'.test-local/pre-r2/bin/fm-captain-hold.sh','hold','duplicate-id','--title','Task in records','--reason','Choose safely'],h,env_extra={'FM_DATA_OVERRIDE':records},out='pre-r2-wrong-backlog.txt')
assert before != (h/'data/backlog.md').read_bytes()
assert 'hold-kind: captain' in (h/'data/backlog.md').read_text()
(E/'pre-r2-default-backlog.md').write_bytes((h/'data/backlog.md').read_bytes())
(E/'counterfactuals.json').write_text(json.dumps({'baseline_commit':'40c50ea8843c5b6a5351db8352675537252b653e','baseline_local_artifact':base_landed.get('local-delivery'),'baseline_reportless_scout_listed':'scout-empty' in base_landed,'pre_r2_commit':'626bfa85','pre_r2_exit':p.returncode,'pre_r2_default_backlog_changed':True,'target_dangling_state':json.loads((E/'config-dangling-state.json').read_text())},indent=2)+'\n')
print('All additional live checks and baseline counterfactuals completed.')
