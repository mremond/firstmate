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
shutil.rmtree(LAB/'config-dangling')
for state in ['dangling','unreadable-project','unreadable-user','absent','readable']:
    h=make_home('config-'+state); records=h/'records';records.mkdir()
    hcfg=h/'.tasks.toml';hcfg.unlink()
    for f in [records/'backlog.md',h/'data/backlog.md']:
        f.write_text('## In flight\n\n## Queued\n\n## Done\n')
        run(['tasks-axi','add','duplicate-id','Task in '+f.parent.name,'--file',f],h,env_extra={'TASKS_AXI_BACKEND':'markdown'})
    uc=LAB/'user-home/.tasks-axi/config.toml';uc.parent.mkdir(exist_ok=True)
    if state=='dangling': hcfg.symlink_to('missing-config.toml')
    if state=='unreadable-project': hcfg.write_text('backend = "markdown"\n');hcfg.chmod(0)
    if state=='unreadable-user': uc.write_text('backend = "beads"\n');uc.chmod(0)
    if state=='readable': hcfg.write_text('backend = "markdown"\n')
    before_default=(h/'data/backlog.md').read_bytes(); before_config=(records/'backlog.md').read_bytes()
    p=run([ROOT/'bin/fm-captain-hold.sh','hold','duplicate-id','--title','Task in records','--reason','Choose safely'],h,expect=None,env_extra={'FM_DATA_OVERRIDE':records},out='config-'+state+'.txt')
    if state in ['dangling','unreadable-project','unreadable-user']:
        assert p.returncode!=0 and 'cannot be read' in p.stderr+p.stdout
        assert (records/'backlog.md').read_bytes()==before_config
        opened=run([ROOT/'bin/fm-captain-hold.sh','open','duplicate-id','--distinguish-absent'],h,expect=2,env_extra={'FM_DATA_OVERRIDE':records})
    else:
        assert p.returncode==0
        assert 'hold-kind: captain' in (records/'backlog.md').read_text()
    assert (h/'data/backlog.md').read_bytes()==before_default
    (E/('config-'+state+'-state.json')).write_text(json.dumps({'exit':p.returncode,'stderr':p.stderr,'default_unchanged':True,'configured_unchanged':(records/'backlog.md').read_bytes()==before_config},indent=2)+'\n')
    if uc.exists(): uc.chmod(0o600);uc.unlink()
    if hcfg.exists() and not hcfg.is_symlink(): hcfg.chmod(0o600)
passed('Holding a task with unreadable or dangling backend configuration refuses without changing either backlog; absent and readable configurations still address the relocated backlog','live-cli-transcript.txt; config-*-state.json')
print(json.dumps(results,indent=2))
